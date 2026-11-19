"""Testes ponta a ponta REAIS: sobem o servidor (uvicorn) e o worker como processos, enviam vídeos reais e esperam o
motor do João (detecção + whisper + ffmpeg) produzir os MP4. Nada é mockado.
Mídia: VM_TEST_MEDIA=<dir> com clip1.mp4 (~45 s, com webcam), vod.mp4 (~4 min), short10.mp4, long16.mp4 (>15 min),
noaudio.mp4 e fake.mp4 (texto). Rodar: VM_TEST_MEDIA=/caminho pytest -x -q web/tests/test_e2e.py"""
import hashlib, hmac, json, os, pathlib, signal, socket, sqlite3, subprocess, sys, tempfile, time
import httpx, pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MEDIA = pathlib.Path(os.environ.get("VM_TEST_MEDIA", "/nonexistent"))
pytestmark = pytest.mark.skipif(not (MEDIA / "clip1.mp4").exists(), reason="defina VM_TEST_MEDIA com vídeos reais")
SECRET = "whsec-test-" + os.urandom(6).hex()
H = {"x-vm": "1"}


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def env():
    data = tempfile.mkdtemp(prefix="vm-e2e-"); port = free_port()
    e = {**os.environ, "VM_DATA_DIR": data, "BETA_SIGNUP": "1", "COOKIE_SECURE": "0", "CAKTO_ENABLED": "1",
         "CAKTO_WEBHOOK_SECRET": SECRET, "CAKTO_OFFER_CREATOR": "off_creator", "CAKTO_OFFER_STUDIO": "off_studio",
         "CAKTO_CHECKOUT_CREATOR": "https://pay.cakto.com.br/creator", "VM_LEASE_S": "12"}
    e.pop("ANTHROPIC_API_KEY", None)
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.app:app", "--port", str(port)], cwd=ROOT, env=e,
                           stdout=open(f"{data}/web.log", "w"), stderr=subprocess.STDOUT)
    st = {"data": pathlib.Path(data), "base": f"http://127.0.0.1:{port}", "env": e, "srv": srv, "worker": None}
    start_worker(st)
    for _ in range(60):
        try:
            if httpx.get(st["base"] + "/healthz").status_code == 200: break
        except httpx.HTTPError: time.sleep(0.5)
    yield st
    for p in (srv, st["worker"]):
        if p and p.poll() is None: p.terminate(); p.wait(10)


def start_worker(st):
    st["worker"] = subprocess.Popen([sys.executable, "-m", "web.worker"], cwd=ROOT, env=st["env"],
                                    stdout=open(st["data"] / "worker.log", "a"), stderr=subprocess.STDOUT)


def client(st):
    return httpx.Client(base_url=st["base"], timeout=120)


def signup(st, email, name="Teste"):
    c = client(st); r = c.post("/api/auth/signup", json={"email": email, "password": "senha-forte-123", "name": name, "accept_terms": True}, headers=H)
    assert r.status_code == 200, r.text; return c


def upload(c, path, name=None, lang="auto"):
    r = c.post("/api/projects", json={"name": name or path.stem, "filename": path.name, "size": path.stat().st_size, "lang": lang}, headers=H)
    if r.status_code != 200: return r
    pid = r.json()["id"]
    return c.put(f"/api/projects/{pid}/source", content=path.read_bytes(), headers=H)


def wait(c, pid, cond, timeout=600):
    t = time.time()
    while time.time() - t < timeout:
        p = c.get(f"/api/projects/{pid}").json()
        if cond(p): return p
        time.sleep(2)
    raise AssertionError(f"timeout esperando projeto {pid}: {p}")


def settled(p):
    return p["status"] in ("done", "failed") and all(i["status"] not in ("queued", "rendering") for i in p.get("items", []))


def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


def hook(st, body, sig=True, secret=SECRET):
    raw = json.dumps(body).encode()
    if sig:
        ts = str(int(time.time())); mac = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
        return httpx.post(st["base"] + "/api/webhooks/cakto", content=raw, headers={"x-cakto-signature": "v1=" + mac, "x-cakto-timestamp": ts})
    return httpx.post(st["base"] + "/api/webhooks/cakto", content=raw)


def event(ev, email, offer, oid):
    return {"event": ev, "data": {"id": oid, "status": "paid", "customer": {"email": email}, "offer": {"id": offer}, "product": {"id": "prod"}}}


# ---------------------------------------------------------------- fluxo principal
def test_fluxo_login_upload_processamento_preview_aprovacao_download(env, tmp_path):
    a = signup(env, "ana@exemplo.com", "Ana")
    assert a.patch("/api/me", json={"handle": "@anaclips"}, headers=H).json()["handle"] == "@anaclips"
    r = upload(a, MEDIA / "clip1.mp4", "Live da Ana"); assert r.status_code == 200, r.text
    pid = r.json()["id"]; env["pid_a"] = pid
    p = wait(a, pid, settled)
    assert p["status"] == "done" and len(p["items"]) == 1, p
    clip = p["items"][0]; assert clip["status"] == "ready", clip; env["clip_a"] = clip["id"]
    prev = a.get(f"/api/clips/{clip['id']}/video"); assert prev.status_code == 200 and len(prev.content) > 100_000
    rng = a.get(f"/api/clips/{clip['id']}/video", headers={"range": "bytes=0-99"}); assert rng.status_code == 206 and len(rng.content) == 100
    assert a.get(f"/api/clips/{clip['id']}/download").status_code == 403          # sem aprovação, sem download
    assert a.post(f"/api/clips/{clip['id']}/approve", headers=H).json()["status"] == "approved"
    d = a.get(f"/api/clips/{clip['id']}/download"); assert d.status_code == 200
    assert "attachment" in d.headers["content-disposition"]
    f = tmp_path / "out.mp4"; f.write_bytes(d.content); info = ffprobe(f)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920) and any(s["codec_type"] == "audio" for s in info["streams"])
    assert abs(float(info["format"]["duration"]) - clip["duration"]) < 1.0
    lib = a.get("/api/library").json(); assert [x["id"] for x in lib] == [clip["id"]]
    assert "#" in a.get(f"/api/clips/{clip['id']}/caption.txt").text


def test_edicao_rerenderiza(env):
    a = client(env); a.post("/api/auth/login", json={"email": "ana@exemplo.com", "password": "senha-forte-123"}, headers=H)
    cid = env["clip_a"]; before = a.get(f"/api/projects/{env['pid_a']}").json()["items"][0]["updated_at"]
    r = a.patch(f"/api/clips/{cid}", json={"screen_title": "TITULO EDITADO", "hashtags": "#um #dois"}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "queued"
    p = wait(a, env["pid_a"], settled); c = p["items"][0]
    assert c["status"] == "ready" and c["copy"]["screen_title"] == "TITULO EDITADO" and c["updated_at"] > before
    assert c["copy"]["hashtags"] == ["#um", "#dois"]


# ---------------------------------------------------------------- isolamento entre clientes
def test_dois_clientes_isolados(env):
    b = signup(env, "bruno@exemplo.com", "Bruno")
    assert b.get("/api/projects").json() == [] and b.get("/api/library").json() == []
    pid, cid = env["pid_a"], env["clip_a"]
    for path in (f"/api/projects/{pid}", f"/api/clips/{cid}/video", f"/api/clips/{cid}/thumb", f"/api/clips/{cid}/download",
                 f"/api/clips/{cid}/caption.txt"):
        assert b.get(path).status_code == 404, path
    assert b.patch(f"/api/clips/{cid}", json={"screen_title": "X"}, headers=H).status_code == 404
    assert b.post(f"/api/clips/{cid}/approve", headers=H).status_code == 404
    assert b.delete(f"/api/projects/{pid}", headers=H).status_code == 404
    r = upload(b, MEDIA / "vod.mp4", "VOD do Bruno"); assert r.status_code == 200, r.text
    p = wait(b, r.json()["id"], settled)
    assert p["status"] == "done" and 1 <= len(p["items"]) <= 3 and all(i["status"] == "ready" for i in p["items"]), p
    assert len(b.get("/api/projects").json()) == 1
    a = client(env); a.post("/api/auth/login", json={"email": "ana@exemplo.com", "password": "senha-forte-123"}, headers=H)
    assert all(x["id"] != r.json()["id"] for x in a.get("/api/projects").json())
    users = {d.name for d in (env["data"] / "users").iterdir()}; assert len(users) == 2  # arquivos separados por cliente


# ---------------------------------------------------------------- erros e segurança
def test_erros_e_seguranca(env):
    c = signup(env, "erros@exemplo.com")
    r = upload(c, MEDIA / "fake.mp4"); assert r.status_code == 400 and "vídeo" in r.json()["detail"]
    r = upload(c, MEDIA / "noaudio.mp4"); assert r.status_code == 400 and "áudio" in r.json()["detail"]
    r = c.post("/api/projects", json={"name": "x", "filename": "a.exe", "size": 10}, headers=H); assert r.status_code == 400
    assert c.post("/api/projects", json={"name": "x", "filename": "a.mp4"}).status_code == 403          # sem header CSRF
    assert httpx.get(env["base"] + "/api/projects").status_code == 401                                 # sem sessão
    assert c.get("/api/me").json()["usage"]["projects"] == 0                                            # falhas não consomem cota
    bad = client(env)
    for _ in range(8): bad.post("/api/auth/login", json={"email": "erros@exemplo.com", "password": "errada"}, headers=H)
    assert bad.post("/api/auth/login", json={"email": "erros@exemplo.com", "password": "senha-forte-123"}, headers=H).status_code == 429
    h = httpx.get(env["base"] + "/"); assert "frame-ancestors 'none'" in h.headers["content-security-policy"]


# ---------------------------------------------------------------- limites do plano
def test_limites_do_plano(env):
    c = signup(env, "limites@exemplo.com")
    r = upload(c, MEDIA / "long16.mp4"); assert r.status_code == 402 and "15 minutos" in r.json()["detail"]   # beta: 15 min
    ids = []
    for k in range(3):
        r = upload(c, MEDIA / "short10.mp4", f"curto {k}")
        if r.status_code == 429:  # limite de projetos simultâneos: espera e tenta de novo
            wait(c, ids[-1], settled); r = upload(c, MEDIA / "short10.mp4", f"curto {k}")
        assert r.status_code == 200, r.text; ids.append(r.json()["id"])
    r = upload(c, MEDIA / "short10.mp4"); assert r.status_code == 402 and "3 projetos" in r.json()["detail"]
    for pid in ids: wait(c, pid, settled)
    assert c.get("/api/me").json()["usage"]["projects"] == 3


# ---------------------------------------------------------------- reinício / recuperação de jobs
def test_worker_morre_no_meio_e_job_e_retomado(env):
    c = signup(env, "crash@exemplo.com")
    r = upload(c, MEDIA / "vod.mp4", "crash"); assert r.status_code == 200; pid = r.json()["id"]
    wait(c, pid, lambda p: p["status"] in ("processing", "rendering"), timeout=120)
    env["worker"].send_signal(signal.SIGKILL); env["worker"].wait()
    db = sqlite3.connect(env["data"] / "app.db")
    stuck = db.execute("SELECT id, attempts FROM jobs WHERE project_id=? AND status='running'", (pid,)).fetchall()
    assert stuck, "esperava um job preso em running após o kill"
    start_worker(env)
    p = wait(c, pid, settled)
    assert p["status"] == "done" and p["items"] and all(i["status"] == "ready" for i in p["items"]), p
    att = db.execute("SELECT attempts FROM jobs WHERE id=?", (stuck[0][0],)).fetchone()[0]
    assert att == stuck[0][1] + 1
    db.close()


# ---------------------------------------------------------------- Cakto
def verify_email(env, email):
    """Não há provedor de e-mail no ambiente: a verificação é marcada direto no banco (ver docs). Planos pagos só são
    aplicados a contas verificadas."""
    db = sqlite3.connect(env["data"] / "app.db"); db.execute("UPDATE users SET email_verified=1 WHERE email=?", (email,)); db.commit(); db.close()


def test_cakto_webhooks(env):
    assert hook(env, event("purchase_approved", "ana@exemplo.com", "off_creator", "o1"), secret="errado").status_code == 401
    assert hook(env, {**event("purchase_approved", "ana@exemplo.com", "off_creator", "o1"), "secret": "errado"}, sig=False).status_code == 401
    a = client(env); a.post("/api/auth/login", json={"email": "ana@exemplo.com", "password": "senha-forte-123"}, headers=H)
    # conta NÃO verificada não recebe plano pago (evita sequestro de assinatura por quem cadastrou o e-mail antes)
    r0 = hook(env, {**event("purchase_approved", "ana@exemplo.com", "off_creator", "o0"), "secret": SECRET}, sig=False)
    assert r0.status_code == 200 and a.get("/api/me").json()["plan"] == "beta"
    verify_email(env, "ana@exemplo.com")
    r = hook(env, {**event("purchase_approved", "ana@exemplo.com", "off_creator", "o1"), "secret": SECRET}, sig=False)
    assert r.json() == {"applied": True, "plan": "creator", "event": "purchase_approved"}
    assert hook(env, {**event("purchase_approved", "ana@exemplo.com", "off_creator", "o1"), "secret": SECRET}, sig=False).json() == {"duplicate": True}
    me = a.get("/api/me").json(); assert me["plan"] == "creator" and me["limits"]["clips_per_project"] == 6
    assert a.get("/api/billing").json()["checkout"] == {"creator": "https://pay.cakto.com.br/creator"}
    # upgrade para Creator Studio (assinatura HMAC)
    assert hook(env, event("purchase_approved", "ana@exemplo.com", "off_studio", "o2")).json()["plan"] == "studio"
    assert a.get("/api/me").json()["plan"] == "studio"
    # renovação atrasada do Creator não rebaixa o Studio vigente
    hook(env, event("subscription_renewed", "ana@exemplo.com", "off_creator", "o3")); assert a.get("/api/me").json()["plan"] == "studio"
    # render premium (SFX + zoom) com o plano Studio
    r = upload(a, MEDIA / "short10.mp4", "premium"); assert r.status_code == 200, r.text
    p = wait(a, r.json()["id"], settled); assert p["items"][0]["status"] == "ready"
    # cancelamento mantém acesso até o fim do período; reembolso corta
    hook(env, event("subscription_canceled", "ana@exemplo.com", "off_studio", "o4"))
    me = a.get("/api/me").json(); assert me["plan"] == "studio" and me["plan_status"] == "canceled"
    hook(env, event("refund", "ana@exemplo.com", "off_studio", "o5")); assert a.get("/api/me").json()["plan"] == "beta"
    # compra antes do cadastro
    hook(env, event("purchase_approved", "nova@exemplo.com", "off_creator", "o6"))
    nv = signup(env, "nova@exemplo.com"); assert nv.get("/api/me").json()["plan"] == "beta"  # sem verificação: não aplica
    verify_email(env, "nova@exemplo.com")
    hook(env, event("subscription_renewed", "nova@exemplo.com", "off_creator", "o6b"))  # próxima cobrança aplica na conta verificada
    assert nv.get("/api/me").json()["plan"] == "creator"
    # vencimento: período expirado volta para o plano de demonstração
    db = sqlite3.connect(env["data"] / "app.db"); db.execute("UPDATE users SET plan_until=? WHERE email='nova@exemplo.com'", (time.time() - 10 * 86400,)); db.commit(); db.close()
    n = client(env); n.post("/api/auth/login", json={"email": "nova@exemplo.com", "password": "senha-forte-123"}, headers=H)
    assert n.get("/api/me").json()["plan"] == "beta"
    n.close()
    # oferta desconhecida não libera nada
    assert hook(env, event("purchase_approved", "x@exemplo.com", "off_outra", "o7")).json()["applied"] is False
