"""Live Monitor multi-transmissão, limites do plano no backend, aceite dos Termos, direitos do titular e MCP.
Não precisa de vídeo nem de agente: sobe só o servidor web e verifica as regras de negócio pela API real (HTTP) e pelo
protocolo MCP real (cliente oficial). O plano pago é aplicado direto no banco (o fluxo Cakto tem teste próprio em test_e2e).
Rodar: pytest -v web/tests/test_monitor.py"""
import asyncio, concurrent.futures, json, os, pathlib, signal, socket, sqlite3, subprocess, sys, tempfile, time
import httpx, pytest, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
H = {"x-vm": "1"}


def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def st():
    data = pathlib.Path(tempfile.mkdtemp(prefix="vm-mon-")); p = port()
    env = {**os.environ, "VM_DATA_DIR": str(data), "BETA_SIGNUP": "1", "COOKIE_SECURE": "0", "PUBLIC_URL": f"http://127.0.0.1:{p}",
           "LIVE_CAPACITY_TOTAL": "100", "LIVE_CAPACITY_BETA": "100",
           # sem agente neste teste: o override pula a consulta à Twitch no início (canais fictícios)
           "LIVE_SOURCE_OVERRIDE": "/sem-agente-neste-teste", "SIGNUP_PER_IP_HOUR": "100", "MCP_RATE_WRITE": "8", "MCP_RATE_READ": "200"}
    env.pop("ANTHROPIC_API_KEY", None)
    for k in ("NO_PROXY", "no_proxy"): env[k] = env.get(k, "") + ",127.0.0.1"
    web = subprocess.Popen([sys.executable, "-m", "uvicorn", "web.app:app", "--port", str(p)], cwd=ROOT, env=env,
                           stdout=open(data / "web.log", "w"), stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{p}"
    for _ in range(60):
        try:
            if httpx.get(base + "/healthz").status_code == 200: break
        except httpx.HTTPError: time.sleep(0.5)
    yield {"data": data, "base": base}
    web.send_signal(signal.SIGTERM); web.wait(20)


def db(S): c = sqlite3.connect(S["data"] / "app.db", isolation_level=None); c.row_factory = sqlite3.Row; return c


def user(S, email, plan=None):
    c = httpx.Client(base_url=S["base"], timeout=30)
    r = c.post("/api/auth/signup", json={"email": email, "password": "senha-forte-123", "accept_terms": True}, headers=H)
    assert r.status_code == 200, r.text
    if plan:
        with db(S) as x:
            x.execute("UPDATE users SET plan=?, plan_status='active', plan_until=?, email_verified=1 WHERE email=?", (plan, time.time() + 30 * 86400, email))
    return c


def connect(c, ch, rights="owner"):
    return c.post("/api/live/streams", json={"channel": ch, "rights_basis": rights}, headers=H)


# ------------------------------------------------------------------------------------------------ limites do plano
@pytest.mark.parametrize("plan,slots", [("creator", 3), ("studio", 10)])
def test_ativacao_das_telas_e_bloqueio_da_proxima(st, plan, slots):
    c = user(st, f"{plan}@mon.com", plan)
    m = c.get("/api/live/monitor").json()
    assert m["slots"] == slots and m["plan"] == ("Creator" if plan == "creator" else "Creator Studio") and m["streams"] == []
    ids = []
    for k in range(slots):
        r = connect(c, f"canal_{plan}_{k}"); assert r.status_code == 200, r.text
        assert r.json()["slot"] == k + 1 and r.json()["state"] == "idle"; ids.append(r.json()["id"])
    extra = connect(c, f"canal_{plan}_extra")
    assert extra.status_code == 403 and f"até {slots} transmiss" in extra.json()["detail"], extra.text   # 4ª (Creator) / 11ª (Studio)
    for sid in ids:
        r = c.post(f"/api/live/streams/{sid}/start", json={"budget_usd": 0.1, "max_minutes": 5}, headers=H); assert r.status_code == 200, r.text
    m = c.get("/api/live/monitor").json()
    assert m["active"] == slots and len(m["streams"]) == slots and all(s["state"] == "starting" for s in m["streams"])
    # já monitorada → 409; sessão extra pela API antiga (canal novo) → bloqueada pelo limite de slots
    assert c.post(f"/api/live/streams/{ids[0]}/start", json={}, headers=H).status_code == 409
    r = c.post("/api/live/sessions", json={"channel": f"canal_{plan}_x2", "rights_basis": "owner"}, headers=H)
    assert r.status_code == 403, r.text
    with db(st) as x:
        n = x.execute("SELECT COUNT(*) FROM live_sessions s JOIN users u ON u.id=s.user_id WHERE u.email=? AND s.status='starting'",
                      (f"{plan}@mon.com",)).fetchone()[0]
    assert n == slots
    # pausar libera a simultaneidade; remover libera o slot para outro canal
    assert c.post(f"/api/live/streams/{ids[0]}/pause", headers=H).json()["status"] == "stopping"
    assert c.delete(f"/api/live/streams/{ids[0]}", headers=H).status_code == 200
    with db(st) as x: x.execute("UPDATE live_sessions SET status='stopped' WHERE status='stopping'")  # o agente faria isso
    assert connect(c, f"canal_{plan}_novo").status_code == 200
    st[plan] = c


def test_corrida_de_inicios_simultaneos_nao_passa_do_limite(st):
    c = user(st, "corrida@mon.com", "creator")
    ids = [connect(c, f"corrida_{k}").json()["id"] for k in range(3)]
    with db(st) as x:  # simula 6 transmissões conectadas antes de um rebaixamento (slots 4–6 acima do plano)
        uid = x.execute("SELECT id FROM users WHERE email='corrida@mon.com'").fetchone()[0]
        for k in range(3, 6):
            x.execute("INSERT INTO live_streams(id,user_id,platform,channel,slot,rights_basis,rights_attested_at,created_at,updated_at) "
                      "VALUES(?,?,'twitch',?,?,'owner',?,?,?)", (f"str_race{k}", uid, f"corrida_{k}", k + 1, time.time(), time.time(), time.time()))
        ids += [f"str_race{k}" for k in range(3, 6)]
    cookies = c.cookies

    def go(sid):
        return httpx.post(f"{st['base']}/api/live/streams/{sid}/start", json={}, headers=H, cookies=cookies, timeout=30).status_code
    with concurrent.futures.ThreadPoolExecutor(6) as ex: codes = list(ex.map(go, ids))
    assert codes.count(200) == 3 and all(k == 403 for k in codes if k != 200), codes
    assert c.get("/api/live/monitor").json()["active"] == 3


def test_rebaixamento_studio_para_creator_bloqueia_slots_excedentes(st):
    c = st["studio"]
    with db(st) as x:
        x.execute("UPDATE live_sessions SET status='stopped', stop_reason='user' WHERE user_id=(SELECT id FROM users WHERE email='studio@mon.com')")
        x.execute("UPDATE users SET plan='creator' WHERE email='studio@mon.com'")
    m = c.get("/api/live/monitor").json(); assert m["slots"] == 3 and len(m["streams"]) == 10
    hi = [s for s in m["streams"] if s["slot"] > 3][0]
    r = c.post(f"/api/live/streams/{hi['id']}/start", json={}, headers=H)
    assert r.status_code == 403 and "acima" in r.json()["detail"]
    assert connect(c, "mais_um").status_code == 403


def test_declaracao_de_direitos_e_validacao(st):
    c = user(st, "direitos@mon.com", "creator")
    r = connect(c, "algum_canal", rights="")
    assert r.status_code == 400 and "titular" in r.json()["detail"]
    assert connect(c, "https://evil.com/x; rm -rf /").status_code == 400
    r = connect(c, "twitch.tv/Canal_Ok", rights="authorized")
    assert r.status_code == 200 and r.json()["channel"] == "canal_ok" and r.json()["rights_basis"] == "authorized"
    assert connect(c, "canal_ok").json()["id"] == r.json()["id"]  # idempotente: não ocupa outro slot


def test_franquia_mensal_bloqueia_inicio(st):
    c = user(st, "franquia@mon.com", "creator")
    sid = connect(c, "canal_franquia").json()["id"]; L = yaml.safe_load((ROOT / "config/plans.yaml").read_text())["plans"]["creator"]
    with db(st) as x:
        uid = x.execute("SELECT id FROM users WHERE email='franquia@mon.com'").fetchone()[0]
        x.execute("INSERT INTO usage(user_id, month, live_s) VALUES(?,?,?)", (uid, time.strftime("%Y-%m", time.gmtime()), L["live_hours_per_month"] * 3600))
    r = c.post(f"/api/live/streams/{sid}/start", json={}, headers=H)
    assert r.status_code == 402 and "franquia" in r.json()["detail"]


def test_beta_tem_um_slot(st):
    env_beta = user(st, "semplano@mon.com")  # BETA_SIGNUP=1 → Beta com 1 slot
    assert connect(env_beta, "beta_1").status_code == 200
    assert connect(env_beta, "beta_2").status_code == 403


# ------------------------------------------------------------------------------------------------ isolamento
def test_isolamento_entre_contas(st):
    a = st["creator"]; b = user(st, "outro@mon.com", "creator")
    sa = a.get("/api/live/monitor").json()["streams"][0]
    assert b.get("/api/live/monitor").json()["streams"] == []
    for method, path in (("post", f"/api/live/streams/{sa['id']}/start"), ("post", f"/api/live/streams/{sa['id']}/pause"),
                         ("delete", f"/api/live/streams/{sa['id']}"), ("get", f"/api/live/streams/{sa['id']}/preview")):
        r = getattr(b, method)(path, headers=H, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 404, (path, r.status_code, r.text)
    if sa["session"]:
        assert b.get(f"/api/live/sessions/{sa['session']['id']}").status_code == 404
    assert httpx.get(st["base"] + "/api/live/monitor").status_code == 401


# ------------------------------------------------------------------------------------------------ Termos versionados
def test_aceite_dos_termos_versionado(st):
    c = httpx.Client(base_url=st["base"], timeout=30)
    r = c.post("/api/auth/signup", json={"email": "semaceite@mon.com", "password": "senha-forte-123"}, headers=H)
    assert r.status_code == 400 and "Termos" in r.json()["detail"]
    c = user(st, "aceite@mon.com", "creator"); me = c.get("/api/me").json()
    assert me["terms"]["required"] is False and me["terms"]["accepted"]["context"] == "signup"
    with db(st) as x:
        row = x.execute("SELECT * FROM terms_acceptances t JOIN users u ON u.id=t.user_id WHERE u.email='aceite@mon.com'").fetchone()
        assert row["terms_version"] == me["terms"]["terms_version"] and abs(row["accepted_at"] - time.time()) < 120
        cols = {r[1] for r in x.execute("PRAGMA table_info(terms_acceptances)")}
        assert cols == {"id", "user_id", "terms_version", "privacy_version", "accepted_at", "context"}  # minimização: sem IP/UA
        x.execute("UPDATE terms_acceptances SET terms_version='2020-01-01' WHERE user_id=(SELECT id FROM users WHERE email='aceite@mon.com')")
    me = c.get("/api/me").json(); assert me["terms"]["required"] is True
    assert connect(c, "precisa_aceite").status_code == 428
    assert c.post("/api/projects", json={"filename": "a.mp4", "size": 10}, headers=H).status_code == 428
    assert c.post("/api/tokens", json={"name": "t", "scopes": ["live:read"]}, headers=H).status_code == 428
    assert c.post("/api/live/sessions/qualquer/clips", json={"start_t": 0, "end_t": 10}, headers=H).status_code == 428
    assert c.patch("/api/clips/qualquer", json={"title": "x"}, headers=H).status_code == 428
    assert c.post("/api/clips/qualquer/approve", headers=H).status_code == 428
    assert c.post("/api/legal/accept", json={"terms_version": "x", "privacy_version": "y"}, headers=H).status_code == 409
    t = me["terms"]; r = c.post("/api/legal/accept", json={"terms_version": t["terms_version"], "privacy_version": t["privacy_version"]}, headers=H)
    assert r.status_code == 200 and r.json()["required"] is False
    assert [h["context"] for h in c.get("/api/legal/status").json()["history"]] == ["signup", "reaccept"]
    assert connect(c, "precisa_aceite").status_code == 200


def test_paginas_juridicas_publicas_e_links(st):
    for doc in ("termos", "privacidade", "cancelamento", "conteudo", "cookies", "regras-live-ia", "contato"):
        r = httpx.get(f"{st['base']}/{doc}"); assert r.status_code == 200, doc
        assert "Versão" in r.text and 'href="/termos"' in r.text and "ClipeiAki" in r.text, doc
        assert "52.467.188" not in r.text and "INNOVATION DIGITAL" not in r.text  # nada de dados do concorrente
    home = httpx.get(st["base"] + "/").text  # visitante sem sessão vê a landing
    for doc in ("termos", "privacidade", "cancelamento", "conteudo", "cookies", "regras-live-ia", "contato"):
        assert f'href="/{doc}"' in home, doc


# ------------------------------------------------------------------------------------------------ direitos do titular
def test_exportar_e_excluir_conta(st):
    c = user(st, "apagar@mon.com", "creator"); connect(c, "canal_apagar")
    with db(st) as x:
        uid = x.execute("SELECT id FROM users WHERE email='apagar@mon.com'").fetchone()[0]
        x.execute("INSERT INTO usage(user_id, month, live_s) VALUES(?,?,60)", (uid, time.strftime("%Y-%m", time.gmtime())))
        x.execute("INSERT INTO jobs(id,user_id,type,status,created_at,updated_at) VALUES('job_x',?,'render','running',?,?)", (uid, time.time(), time.time()))
    ex = c.get("/api/me/export"); assert ex.status_code == 200
    d = ex.json(); assert d["account"]["email"] == "apagar@mon.com" and d["live_streams"][0]["channel"] == "canal_apagar"
    assert "pw_hash" not in ex.text and "token_hash" not in ex.text
    assert c.request("DELETE", "/api/me", json={"password": "errada"}, headers=H).status_code == 403
    assert c.request("DELETE", "/api/me", json={"password": "senha-forte-123"}, headers=H).status_code == 200
    with db(st) as x:
        assert x.execute("SELECT COUNT(*) FROM users WHERE email='apagar@mon.com'").fetchone()[0] == 0
        assert x.execute("SELECT COUNT(*) FROM live_streams WHERE channel='canal_apagar'").fetchone()[0] == 0
        assert x.execute("SELECT COUNT(*) FROM terms_acceptances WHERE user_id NOT IN (SELECT id FROM users)").fetchone()[0] == 0
        assert x.execute("SELECT COUNT(*) FROM usage WHERE user_id=?", (uid,)).fetchone()[0] == 0
        assert x.execute("SELECT COUNT(*) FROM jobs WHERE user_id=?", (uid,)).fetchone()[0] == 0
        assert x.execute("SELECT COUNT(*) FROM access_logs WHERE user_id=?", (uid,)).fetchone()[0] >= 1  # Marco Civil: fica 6 meses
    assert c.get("/api/me").status_code == 401


# ------------------------------------------------------------------------------------------------ planos (fonte única)
def test_planos_publicos_iguais_ao_backend(st):
    P = yaml.safe_load((ROOT / "config/plans.yaml").read_text())["plans"]
    r = httpx.get(st["base"] + "/api/public/plans").json()
    assert r["plans"]["creator"]["label"] == "Creator" and r["plans"]["creator"]["price_brl"] == 49.90 and r["plans"]["creator"]["live_slots"] == 3
    assert r["plans"]["studio"]["label"] == "Creator Studio" and r["plans"]["studio"]["price_brl"] == 69.90 and r["plans"]["studio"]["live_slots"] == 10
    for k in ("creator", "studio"):
        for f, v in r["plans"][k].items(): assert P[k][f] == v, (k, f)
    assert r["checkout_enabled"] is False  # P0: cobrança desligada até homologação


# ------------------------------------------------------------------------------------------------ MCP
async def mcp_calls(S, token, calls):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    out = []
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60) as hc:
        async with Client(streamable_http_client(S["base"] + "/mcp", http_client=hc)) as cl:
            if calls == "list": return sorted(t.name for t in (await cl.list_tools()).tools)
            for name, args in calls:
                r = await cl.call_tool(name, args)
                out.append({"error": r.is_error, "text": "".join(getattr(c, "text", "") for c in r.content),
                            "types": [c.type for c in r.content]})
    return out


def token(c, scopes, days=90):
    r = c.post("/api/tokens", json={"name": "mcp", "scopes": scopes, "days": days}, headers=H); assert r.status_code == 200, r.text
    return r.json()


def test_mcp_ferramentas_auth_isolamento_e_limites(st):
    a = user(st, "mcp-a@mon.com", "creator"); b = user(st, "mcp-b@mon.com", "creator")
    ta = token(a, ["live:read", "live:control", "clips:read", "clips:write"])["token"]; tb = token(b, ["live:read"])["token"]
    names = asyncio.run(mcp_calls(st, ta, "list"))
    for n in ("list_connected_streamers", "connect_stream", "start_monitoring", "stop_monitoring", "get_live_status", "get_live_preview",
              "list_detected_moments", "get_highlight", "create_clip", "approve_clip", "list_render_jobs"):
        assert n in names, n
    r = asyncio.run(mcp_calls(st, ta, [("connect_stream", {"channel": "mcp_canal", "rights_basis": "owner"}),
                                       ("connect_stream", {"channel": "sem_declaracao", "rights_basis": "talvez"}),
                                       ("start_monitoring", {"channel": "mcp_canal", "budget_usd": 0.1, "max_minutes": 5}),
                                       ("list_connected_streamers", {}), ("list_render_jobs", {})]))
    assert not r[0]["error"] and r[1]["error"] and not r[2]["error"], r
    sid = json.loads(r[0]["text"])["id"]; mon = json.loads(r[3]["text"])
    assert mon["slots"] == 3 and mon["streams"][0]["state"] == "starting"
    # B não enxerga nem controla nada de A; e não tem escopo de controle
    rb = asyncio.run(mcp_calls(st, tb, [("get_live_status", {"stream_id": sid}), ("get_live_preview", {"stream_id": sid}),
                                        ("stop_monitoring", {"stream_id": sid}), ("list_connected_streamers", {})]))
    assert rb[0]["error"] and "não encontrada" in rb[0]["text"] and rb[1]["error"] and "não encontrada" in rb[1]["text"]
    assert rb[2]["error"] and "live:control" in rb[2]["text"]
    assert json.loads(rb[3]["text"])["streams"] == []
    # preview só existe quando há frame gravado de verdade (aqui ninguém gravou)
    rp = asyncio.run(mcp_calls(st, ta, [("get_live_preview", {"stream_id": sid}), ("approve_clip", {"clip_id": "clip_inexistente"})]))
    assert rp[0]["error"] and "frame gravado" in rp[0]["text"] and rp[1]["error"]
    # limite de requisições de escrita por token (MCP_RATE_WRITE=8 neste teste)
    rs = asyncio.run(mcp_calls(st, ta, [("stop_monitoring", {"stream_id": sid})] * 10))
    assert any(x["error"] and "Limite de 8" in x["text"] for x in rs), [x["text"][:60] for x in rs]
    # tokens: expirado e revogado → 401; sem token → 401
    t = token(a, ["live:read"], days=1)
    with db(st) as x: x.execute("UPDATE api_tokens SET expires_at=? WHERE id=?", (time.time() - 1, t["id"]))
    hdr = lambda k: {"Authorization": f"Bearer {k}", "content-type": "application/json", "accept": "application/json, text/event-stream"}
    assert httpx.post(st["base"] + "/mcp", headers=hdr(t["token"]), json={}).status_code == 401
    assert httpx.post(st["base"] + "/mcp", json={}).status_code == 401
    assert a.post("/api/tokens", json={"name": "x", "scopes": ["live:read"], "days": 999}, headers=H).status_code == 400
    with db(st) as x:
        assert x.execute("SELECT COUNT(*) FROM api_tokens WHERE token_hash LIKE 'cak_%'").fetchone()[0] == 0  # só hash no banco
