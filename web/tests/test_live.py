"""Testes do Claude Live Agent + MCP.
TIPOS DE EVIDÊNCIA (não misturar):
  [SIM]  fonte = vídeo real de gameplay tocado em tempo real como se fosse live (LIVE_SOURCE_OVERRIDE) e Claude API
         substituída pelo servidor local web/tests/fake_claude.py. Prova o nosso pipeline (gravação, segmentos, detecção,
         frames enviados, validação, orçamento, falhas, recuperação, isolamento, MCP, render) — NÃO prova a qualidade do Claude.
  [REAL] ver test_live_real.py (Twitch ao vivo de verdade; Claude real só com ANTHROPIC_API_KEY).
Rodar: VM_TEST_MEDIA=<dir com vod.mp4> pytest -v web/tests/test_live.py"""
import asyncio, base64, hashlib, json, os, pathlib, signal, socket, sqlite3, subprocess, sys, tempfile, time
import httpx, pytest
from .fake_claude import FakeClaude

ROOT = pathlib.Path(__file__).resolve().parents[2]
MEDIA = pathlib.Path(os.environ.get("VM_TEST_MEDIA", "/nonexistent"))
pytestmark = pytest.mark.skipif(not (MEDIA / "vod.mp4").exists(), reason="defina VM_TEST_MEDIA com vod.mp4")
H = {"x-vm": "1"}


def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def st():
    data = pathlib.Path(tempfile.mkdtemp(prefix="vm-live-")); p = port(); fake = FakeClaude(usage=(2500, 500))
    env = {**os.environ, "VM_DATA_DIR": str(data), "BETA_SIGNUP": "1", "COOKIE_SECURE": "0", "PUBLIC_URL": f"http://127.0.0.1:{p}",
           "ANTHROPIC_API_KEY": "sk-ant-SIMULADO-nao-e-chave-real", "VM_ANTHROPIC_BASE_URL": fake.url, "LIVE_CLAUDE_ENABLED": "1",  # caminho opcional (desligado por padrão)
           "LIVE_SOURCE_OVERRIDE": str(MEDIA / "vod.mp4"), "LIVE_SEGMENT_S": "5", "LIVE_PRE_S": "6", "LIVE_POST_S": "4",
           "LIVE_COOLDOWN_S": "8", "LIVE_AUDIO_DB": "3", "LIVE_MIN_CALL_INTERVAL_S": "0", "LIVE_LEASE_S": "8", "LIVE_OFFLINE_S": "60",
           "VM_LEASE_S": "30", "LIVE_SSE_MAX_S": "60"}
    for k in ("NO_PROXY", "no_proxy"): env[k] = env.get(k, "") + ",127.0.0.1"
    S = {"data": data, "base": f"http://127.0.0.1:{p}", "env": env, "fake": fake, "procs": {}}
    S["procs"]["web"] = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.app:app", "--port", str(p)], cwd=ROOT, env=env,
                                         stdout=open(data / "web.log", "w"), stderr=subprocess.STDOUT)
    S["procs"]["worker"] = subprocess.Popen([sys.executable, "-m", "web.worker"], cwd=ROOT, env=env, stdout=open(data / "worker.log", "w"), stderr=subprocess.STDOUT)
    start_agent(S)
    for _ in range(60):
        try:
            if httpx.get(S["base"] + "/healthz").status_code == 200: break
        except httpx.HTTPError: time.sleep(0.5)
    yield S
    for pr in S["procs"].values():
        if pr.poll() is None: pr.send_signal(signal.SIGTERM)
    for pr in S["procs"].values():
        try: pr.wait(20)
        except subprocess.TimeoutExpired: pr.kill()
    fake.close()


def start_agent(S):
    S["procs"]["agent"] = subprocess.Popen([sys.executable, "-m", "web.live.agent"], cwd=ROOT, env=S["env"],
                                           stdout=open(S["data"] / "agent.log", "a"), stderr=subprocess.STDOUT)


def user(S, email):
    c = httpx.Client(base_url=S["base"], timeout=60)
    assert c.post("/api/auth/signup", json={"email": email, "password": "senha-forte-123", "accept_terms": True}, headers=H).status_code == 200
    return c


def db(S): c = sqlite3.connect(S["data"] / "app.db"); c.row_factory = sqlite3.Row; return c


def wait(fn, timeout=300, every=2, msg=""):
    t = time.time()
    while time.time() - t < timeout:
        r = fn()
        if r: return r
        time.sleep(every)
    raise AssertionError(f"timeout: {msg}")


def events(S, sid, kind=None):
    with db(S) as c:
        q = "SELECT * FROM live_events WHERE session_id=?" + (" AND kind=?" if kind else "") + " ORDER BY id"
        return [{**dict(r), "data": json.loads(r["data"])} for r in c.execute(q, (sid, *([kind] if kind else [])))]


def segments(S, sid):
    with db(S) as c: return [dict(r) for r in c.execute("SELECT * FROM live_segments WHERE session_id=? AND duration>0 ORDER BY seq", (sid,))]


def stop(S, cl, sid):
    cl.post(f"/api/live/sessions/{sid}/stop", headers=H)
    wait(lambda: cl.get(f"/api/live/sessions/{sid}").json()["status"] == "stopped", 120, msg="parar sessão")


def contiguous(segs):
    for a, b in zip(segs, segs[1:]):
        assert abs(b["t_start"] - (a["t_start"] + a["duration"])) < 0.06, (a, b)


# ------------------------------------------------------------------------------------------------ [SIM]
def test_sim_monitoramento_analise_frames_e_corte_durante_gravacao(st):
    a = user(st, "ana@live.com"); st["a"] = a
    r = a.post("/api/live/sessions", json={"channel": "twitch.tv/canal_simulado", "budget_usd": 0.5, "max_minutes": 10, "rights_basis": "owner"}, headers=H)
    assert r.status_code == 200, r.text; sid = r.json()["id"]; st["sid_a"] = sid
    assert r.json()["claude"]["configured"] is True
    # SSE: eventos reais do backend com id crescente
    seen = []
    with httpx.stream("GET", f"{st['base']}/api/live/sessions/{sid}/events", cookies=a.cookies, timeout=120) as s:
        for line in s.iter_lines():
            if line.startswith("data:") and '"kind"' in line:
                seen.append(json.loads(line[5:]))
                if any(e["kind"] == "analysis" for e in seen): break
    ids = [e["id"] for e in seen]; assert ids == sorted(ids) and len(set(ids)) == len(ids)
    an = next(e for e in seen if e["kind"] == "analysis")
    # frame mostrado = frame enviado: sha do arquivo servido == sha registrado == sha dos bytes que chegaram à "API"
    sent = {h for req in st["fake"].requests for h in req["image_sha256"]}
    for f in an["data"]["frames"]:
        img = a.get(f"/api/live/frames/{f['id']}"); assert img.status_code == 200
        assert hashlib.sha256(img.content).hexdigest() == f["sha256"] == img.headers["x-frame-sha256"]
        assert f["sha256"] in sent
    # alinhamento: frames dentro da janela do momento; decisão dentro da janela
    m = next(x for x in a.get(f"/api/live/sessions/{sid}").json()["moments"] if x["id"] == an["data"]["moment_id"])
    assert all(m["w_start"] <= f["t"] <= m["w_end"] for f in an["data"]["frames"])
    assert m["w_start"] <= an["data"]["start_t"] < an["data"]["end_t"] <= m["w_end"]
    assert abs(an["t_stream"] - m["peak"]) < 0.01
    # corte gerado pelo motor enquanto a gravação continua
    clip_ev = wait(lambda: events(st, sid, "clip_ready"), 300, msg="corte pronto")[0]
    q = next(e for e in events(st, sid, "clip_queued") if e["data"]["clip_id"] == clip_ev["data"]["clip_id"])
    assert abs(q["data"]["start_t"] - an["data"]["start_t"]) < 0.01 or q["data"]["moment_id"] != an["data"]["moment_id"]
    with db(st) as c:
        j = c.execute("SELECT created_at, updated_at FROM jobs WHERE clip_id=? AND type='render'", (clip_ev["data"]["clip_id"],)).fetchone()
        during = c.execute("SELECT COUNT(*) FROM live_segments WHERE session_id=? AND created_at BETWEEN ? AND ?", (sid, j[0], j[1])).fetchone()[0]
    assert during >= 1, "nenhum segmento gravado enquanto o corte renderizava"
    v = a.get(f"/api/clips/{clip_ev['data']['clip_id']}/video"); assert v.status_code == 200
    vp = st["data"] / "clip_check.mp4"; vp.write_bytes(v.content)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vp)],
                               capture_output=True, text=True).stdout)
    assert abs(dur - (q["data"]["end_t"] - q["data"]["start_t"])) < 0.6, (dur, q["data"])  # corte tem a duração decidida
    contiguous(segments(st, sid))
    walls = [e["wall_at"] for e in events(st, sid)]; assert walls == sorted(walls)
    # chave nunca vai ao navegador
    for path in (f"/api/live/sessions/{sid}", "/api/me", "/static/app.js", "/static/live.js"):
        assert "sk-ant-SIMULADO" not in a.get(path).text
    hdr = {k.lower(): v for k, v in st["fake"].requests[0]["headers"].items()}
    sent_key = hdr.get("x-api-key") or hdr.get("authorization", "").removeprefix("Bearer ")
    assert sent_key == "sk-ant-SIMULADO-nao-e-chave-real"  # a chave só sai do servidor para a API
    stop(st, a, sid)
    assert segments(st, sid) and all(x["deleted"] for x in db(st).execute("SELECT deleted FROM live_segments WHERE session_id=?", (sid,)))


def test_sim_falha_do_claude_e_reconexao_do_stream(st):
    b = user(st, "bia@live.com"); st["fake"].fail_left = 2  # chamada + 1 retentativa do SDK falham
    sid = b.post("/api/live/sessions", json={"channel": "canal_simulado", "budget_usd": 0.5, "max_minutes": 10, "rights_basis": "owner"}, headers=H).json()["id"]
    err = wait(lambda: events(st, sid, "claude_error"), 200, msg="erro do Claude")[0]
    assert "500" in err["data"]["error"] or "Erro da API" in err["data"]["error"]
    wait(lambda: events(st, sid, "analysis"), 200, msg="análise após o erro")
    assert b.get(f"/api/live/sessions/{sid}").json()["claude"]["state"] in ("ok", "calling")
    with db(st) as c: pgid = c.execute("SELECT recorder_pgid FROM live_sessions WHERE id=?", (sid,)).fetchone()[0]
    os.killpg(pgid, signal.SIGKILL)  # derruba a gravação
    wait(lambda: events(st, sid, "disconnected"), 60, msg="desconexão")
    wait(lambda: events(st, sid, "reconnected"), 90, msg="reconexão")
    contiguous(segments(st, sid)); stop(st, b, sid)


def test_sim_reinicio_do_agente_retoma_sessao(st):
    c_ = user(st, "caio@live.com"); st["fake"].decision = "skip"
    sid = c_.post("/api/live/sessions", json={"channel": "canal_simulado", "budget_usd": 0.5, "max_minutes": 10, "rights_basis": "owner"}, headers=H).json()["id"]
    wait(lambda: len(segments(st, sid)) >= 3, 120, msg="segmentos antes do kill")
    with db(st) as c: pgid = c.execute("SELECT recorder_pgid FROM live_sessions WHERE id=?", (sid,)).fetchone()[0]
    st["procs"]["agent"].send_signal(signal.SIGKILL); st["procs"]["agent"].wait()
    n = len(segments(st, sid)); start_agent(st)
    wait(lambda: events(st, sid, "resumed"), 60, msg="sessão retomada")
    with pytest.raises(ProcessLookupError): os.killpg(pgid, 0)  # gravador órfão foi encerrado
    wait(lambda: len(segments(st, sid)) >= n + 3, 120, msg="gravação continua após reinício")
    contiguous(segments(st, sid)); stop(st, c_, sid)


def test_sim_orcamento_reduz_frames_e_encerra(st):
    d = user(st, "duda@live.com"); st["fake"].decision = "skip"; n0 = len(st["fake"].requests)
    # cada chamada simulada custa 2500*4/1e6 + 500*20/1e6 = US$ 0,02; antes de cada chamada o agente reserva o pior caso
    # (max_tokens inteiro de saída ≈ US$ 0,07) e para quando gasto + reserva passaria do orçamento
    sid = d.post("/api/live/sessions", json={"channel": "canal_simulado", "budget_usd": 0.20, "max_minutes": 10, "rights_basis": "owner"}, headers=H).json()["id"]
    s = wait(lambda: (x := d.get(f"/api/live/sessions/{sid}").json())["status"] == "stopped" and x, 400, 3, msg="encerrar por orçamento")
    assert s["stop_reason"] == "budget", s["stop_reason"]
    assert s["spent_usd"] <= s["budget_usd"] + 1e-9
    frames = [len(r["image_sha256"]) for r in st["fake"].requests[n0:]]
    started = [e["data"] for e in events(st, sid, "analysis_started")]
    planned = [x["frames_planned"] for x in started]
    # política de redução: 3 frames até 50% do orçamento, 2 até 80%, depois 1 (frames antes do início da live não existem)
    assert planned == sorted(planned, reverse=True) and planned[-1] < planned[0], planned
    for x in started:
        frac = x["spent_before_usd"] / 0.20
        assert x["frames_planned"] == (3 if frac < 0.5 else 2 if frac < 0.8 else 1), x
        assert len(x["frames_t"]) <= x["frames_planned"]
    assert len(frames) == len(started) >= 3 and all(f <= p for f, p in zip(frames, planned)), (frames, planned)
    assert abs(s["spent_usd"] - 0.02 * len(frames)) < 1e-6 and s["calls"] == len(frames)
    assert events(st, sid, "limit")[0]["data"]["reason"] == "budget"


def test_isolamento_entre_usuarios_e_tokens(st):
    a, sid = st["a"], st["sid_a"]; x = user(st, "intruso@live.com")
    an = events(st, sid, "analysis")[0]; fid = an["data"]["frames"][0]["id"]; mid = an["data"]["moment_id"]
    for path in (f"/api/live/sessions/{sid}", f"/api/live/sessions/{sid}/context", f"/api/live/frames/{fid}", f"/api/live/sessions/{sid}/events"):
        assert x.get(path).status_code == 404, path
    assert x.post(f"/api/live/sessions/{sid}/stop", headers=H).status_code == 404
    assert x.post(f"/api/live/sessions/{sid}/clips", json={"moment_id": mid}, headers=H).status_code == 404
    assert x.post("/api/live/sessions", json={"channel": "https://evil.com/x; rm -rf /"}, headers=H).status_code == 400
    assert x.get("/api/live/sessions").json() == []
    tok = x.post("/api/tokens", json={"name": "t", "scopes": ["live:read", "clips:read"]}, headers=H).json()
    res = asyncio.run(mcp_calls(st, tok["token"], [("get_live_status", {"stream_id": a.get(f"/api/live/sessions/{sid}").json()["stream_id"]}), ("start_monitoring", {"channel": "xqc"})]))
    assert res[0]["error"] and "não encontrada" in res[0]["text"]  # transmissão de outro usuário
    assert res[1]["error"] and "live:control" in res[1]["text"]
    assert x.delete(f"/api/tokens/{tok['id']}", headers=H).status_code == 200
    r = httpx.post(st["base"] + "/mcp", headers={"Authorization": f"Bearer {tok['token']}", "content-type": "application/json"}, json={})
    assert r.status_code == 401
    assert httpx.post(st["base"] + "/mcp", json={}).status_code == 401


async def mcp_calls(S, token, calls):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    out = []
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=120) as hc:
        async with Client(streamable_http_client(S["base"] + "/mcp", http_client=hc)) as cl:
            for name, args in calls:
                r = await cl.call_tool(name, args)
                txt = "".join(getattr(c, "text", "") for c in r.content)
                imgs = [hashlib.sha256(base64.b64decode(c.data)).hexdigest() for c in r.content if getattr(c, "type", "") == "image"]
                out.append({"error": r.is_error, "text": txt, "data": r.structured_content, "images": imgs})
    return out


def test_mcp_ferramentas_controlam_o_agente(st):
    e = user(st, "edu@live.com"); st["fake"].decision = "skip"
    tok = e.post("/api/tokens", json={"name": "mcp", "scopes": ["live:read", "live:control", "clips:read", "clips:write"]}, headers=H).json()["token"]
    r = asyncio.run(mcp_calls(st, tok, [("connect_stream", {"channel": "canal_simulado", "rights_basis": "owner"}),
                                        ("start_monitoring", {"channel": "canal_simulado", "budget_usd": 0.3, "max_minutes": 5}),
                                        ("list_connected_streamers", {})]))
    assert not r[0]["error"], r[0]; r = r[1:]
    assert not r[0]["error"], r[0]; sid = json.loads(r[0]["text"])["id"] if not r[0]["data"] else r[0]["data"]["id"]
    wait(lambda: len(segments(st, sid)) >= 4, 120, msg="segmentos via MCP")
    # preview REAL pelo MCP: a imagem recebida no protocolo é o mesmo arquivo que a API serve para a grade
    stream_id = e.get(f"/api/live/sessions/{sid}").json()["stream_id"]
    wait(lambda: e.get("/api/live/monitor").json()["streams"][0]["session"]["preview"], 60, msg="preview gravado")
    pv = asyncio.run(mcp_calls(st, tok, [("get_live_preview", {"stream_id": stream_id})]))[0]
    rest = e.get(f"/api/live/streams/{stream_id}/preview")
    assert not pv["error"] and len(pv["images"]) == 1 and rest.status_code == 200, pv["text"][:200]
    meta = json.loads(pv["text"]); assert meta["session_id"] == sid and meta["t_stream"] <= segments(st, sid)[-1]["t_start"] + 10.5
    assert pv["images"][0] == hashlib.sha256(rest.content).hexdigest() or float(rest.headers["x-preview-wall"]) > meta["wall_at"]  # pode ter avançado um bloco
    # evidências de um momento analisado: as imagens do get_highlight são exatamente os frames enviados ao "Claude"
    an = wait(lambda: events(st, sid, "analysis"), 240, msg="análise na sessão do MCP")[0]
    hl = asyncio.run(mcp_calls(st, tok, [("get_highlight", {"moment_id": an["data"]["moment_id"]})]))[0]
    assert not hl["error"] and hl["images"] == [f["sha256"] for f in an["data"]["frames"]][:3], (hl["images"], an["data"]["frames"])
    sent = {h for req in st["fake"].requests for h in req["image_sha256"]}
    assert set(hl["images"]) <= sent and json.loads(hl["text"])["decision"]["decision"] == "skip"
    ctx, moms = asyncio.run(mcp_calls(st, tok, [("get_recent_context", {"session_id": sid, "seconds": 60}), ("list_detected_moments", {"session_id": sid})]))
    assert not ctx["error"] and "segments" in ctx["text"]
    segs = segments(st, sid); a0 = segs[-3]["t_start"]
    cr = asyncio.run(mcp_calls(st, tok, [("create_clip", {"session_id": sid, "start_t": a0, "end_t": a0 + 8})]))[0]
    assert not cr["error"], cr
    mid = json.loads(cr["text"])["moment_id"] if not cr["data"] else cr["data"]["moment_id"]
    clip_id = wait(lambda: db(st).execute("SELECT clip_id FROM live_moments WHERE id=?", (mid,)).fetchone()[0], 120, msg="clip_id")
    wait(lambda: '"ready"' in asyncio.run(mcp_calls(st, tok, [("get_render_status", {"clip_id": clip_id})]))[0]["text"], 240, 4, msg="render via MCP")
    lc, ap, sp = asyncio.run(mcp_calls(st, tok, [("list_render_jobs", {}), ("approve_clip", {"clip_id": clip_id}),
                                                 ("stop_monitoring", {"session_id": sid})]))
    assert clip_id in lc["text"] and not sp["error"]
    assert not ap["error"] and '"approved"' in ap["text"], ap
    wait(lambda: e.get(f"/api/live/sessions/{sid}").json()["status"] == "stopped", 120, msg="parar via MCP")
