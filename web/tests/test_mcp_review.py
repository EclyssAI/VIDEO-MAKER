"""Fluxo principal do produto: servidor SEM API do Claude; quem decide os cortes é o Claude do CLIENTE pelo MCP.
[SIM] fonte = VOD real tocado como live (LIVE_SOURCE_OVERRIDE). O "Claude do cliente" aqui é um cliente MCP oficial
(SDK) autenticado por OAuth exatamente como o conector do claude.ai: as decisões são escritas pelo teste, então isto prova
o pipeline (evidências reais → decisão → corte → aprovação), não a qualidade de um modelo.
Rodar: VM_TEST_MEDIA=<dir com vod.mp4> pytest -v web/tests/test_mcp_review.py"""
import asyncio, base64, hashlib, json, os, pathlib, secrets, signal, socket, sqlite3, subprocess, sys, tempfile, time
from urllib.parse import parse_qs, urlparse
import httpx, pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MEDIA = pathlib.Path(os.environ.get("VM_TEST_MEDIA", "/nonexistent"))
pytestmark = pytest.mark.skipif(not (MEDIA / "vod.mp4").exists(), reason="defina VM_TEST_MEDIA com vod.mp4")
H = {"x-vm": "1"}


def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def st():
    data = pathlib.Path(tempfile.mkdtemp(prefix="vm-review-")); p = port(); base = f"http://127.0.0.1:{p}"
    env = {**os.environ, "VM_DATA_DIR": str(data), "BETA_SIGNUP": "1", "COOKIE_SECURE": "0", "PUBLIC_URL": base,
           "LIVE_SOURCE_OVERRIDE": str(MEDIA / "vod.mp4"), "LIVE_SEGMENT_S": "5", "LIVE_PRE_S": "6", "LIVE_POST_S": "4",
           "LIVE_COOLDOWN_S": "8", "LIVE_AUDIO_DB": "3", "LIVE_LEASE_S": "8", "LIVE_OFFLINE_S": "60"}
    env.pop("ANTHROPIC_API_KEY", None); env.pop("LIVE_CLAUDE_ENABLED", None)  # sem API no servidor (padrão do produto)
    for k in ("NO_PROXY", "no_proxy"): env[k] = env.get(k, "") + ",127.0.0.1"
    procs = [subprocess.Popen([sys.executable, "-m", "uvicorn", "web.app:app", "--port", str(p)], cwd=ROOT, env=env, stdout=open(data / "web.log", "w"), stderr=subprocess.STDOUT),
             subprocess.Popen([sys.executable, "-m", "web.worker"], cwd=ROOT, env=env, stdout=open(data / "worker.log", "w"), stderr=subprocess.STDOUT),
             subprocess.Popen([sys.executable, "-m", "web.live.agent"], cwd=ROOT, env=env, stdout=open(data / "agent.log", "w"), stderr=subprocess.STDOUT)]
    for _ in range(60):
        try:
            if httpx.get(base + "/healthz").status_code == 200: break
        except httpx.HTTPError: time.sleep(0.5)
    yield {"base": base, "data": data}
    for pr in procs: pr.send_signal(signal.SIGTERM)
    for pr in procs:
        try: pr.wait(20)
        except subprocess.TimeoutExpired: pr.kill()


def wait(fn, timeout=300, every=2, msg=""):
    t = time.time()
    while time.time() - t < timeout:
        r = fn()
        if r: return r
        time.sleep(every)
    raise AssertionError(f"timeout: {msg}")


def oauth_token(base, cookie_client):
    asm = httpx.get(base + "/.well-known/oauth-authorization-server").json(); cb = "https://claude.ai/api/mcp/auth_callback"
    cid = httpx.post(asm["registration_endpoint"], json={"client_name": "Claude", "redirect_uris": [cb], "token_endpoint_auth_method": "none",
                                                         "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}).json()["client_id"]
    v = secrets.token_urlsafe(48); ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    r = httpx.get(asm["authorization_endpoint"], params={"response_type": "code", "client_id": cid, "redirect_uri": cb, "code_challenge": ch,
                                                         "code_challenge_method": "S256", "state": "s"})
    rid = parse_qs(urlparse(r.headers["location"]).query)["req"][0]
    red = cookie_client.post(f"/api/oauth/requests/{rid}", json={"approve": True}, headers=H).json()["redirect"]
    code = parse_qs(urlparse(red).query)["code"][0]
    return httpx.post(asm["token_endpoint"], data={"grant_type": "authorization_code", "code": code, "redirect_uri": cb, "client_id": cid,
                                                   "code_verifier": v}).json()["access_token"]


async def mcp(base, token, calls):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    out = []
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=120) as hc:
        async with Client(streamable_http_client(base + "/mcp", http_client=hc)) as cl:
            for name, args in calls:
                if name == "@prompt":
                    pr = await cl.get_prompt("revisar_momentos", args); out.append({"prompt": pr.messages[0].content.text}); continue
                r = await cl.call_tool(name, args)
                out.append({"error": r.is_error, "text": "".join(getattr(c, "text", "") for c in r.content), "data": r.structured_content,
                            "images": [hashlib.sha256(base64.b64decode(c.data)).hexdigest() for c in r.content if getattr(c, "type", "") == "image"]})
    return out


def items(res):
    """Ferramentas que devolvem lista vêm como conteúdo estruturado {"result": [...]}."""
    d = res.get("data")
    return d.get("result", d) if isinstance(d, dict) else json.loads(res["text"] or "[]")


def test_claude_do_cliente_revisa_e_corta_via_mcp(st):
    base = st["base"]; u = httpx.Client(base_url=base, timeout=60)
    assert u.post("/api/auth/signup", json={"email": "cliente@review.com", "password": "senha-forte-123", "accept_terms": True}, headers=H).status_code == 200
    tok = oauth_token(base, u)
    r = asyncio.run(mcp(base, tok, [("@prompt", {}), ("connect_stream", {"channel": "canal_review", "rights_basis": "owner"}),
                                     ("start_monitoring", {"channel": "canal_review", "max_minutes": 10})]))
    assert "review_moment" in r[0]["prompt"] and not r[1]["error"] and not r[2]["error"], r
    sid = json.loads(r[2]["text"])["id"]; stream_id = json.loads(r[1]["text"])["id"]
    mon = u.get("/api/live/monitor").json(); assert mon["claude"]["state"] == "disabled" and mon["mcp_last_use"]  # sem API; MCP em uso
    # candidatos detectados localmente ficam esperando a revisão do Claude do cliente
    cands = wait(lambda: [m for m in items(asyncio.run(mcp(base, tok, [("list_detected_moments", {"stream_id": stream_id, "status": "candidate"})]))[0])
                          if m["w_end"] <= u.get(f"/api/live/sessions/{sid}").json()["recorded_s"]], 240, 3, msg="candidatos")
    m1 = cands[0]
    hl = asyncio.run(mcp(base, tok, [("get_highlight", {"moment_id": m1["id"]})]))[0]
    h = json.loads(hl["text"]); assert not hl["error"] and 1 <= len(hl["images"]) <= 3
    assert hl["images"] == [f["sha256"] for f in h["frames_sent_to_claude"]]  # imagens = frames registrados como mostrados
    for f in h["frames_sent_to_claude"]:  # o mesmo arquivo é servido ao usuário no app, com o mesmo SHA-256
        img = u.get(f"/api/live/frames/{f['id']}"); assert hashlib.sha256(img.content).hexdigest() == f["sha256"]
        assert m1["w_start"] <= f["t_stream"] <= m1["w_end"]
    # decisão inválida (fora da janela) é recusada; válida vira corte pelo motor existente
    bad = asyncio.run(mcp(base, tok, [("review_moment", {"moment_id": m1["id"], "decision": "clip", "confidence": 0.9, "reason": "x",
                                                         "start_t": m1["w_end"] + 100, "end_t": m1["w_end"] + 130})]))[0]
    assert bad["error"] and "inválida" in bad["text"]
    a, b = m1["w_start"], min(m1["w_end"], m1["w_start"] + 12)
    ok = asyncio.run(mcp(base, tok, [("review_moment", {"moment_id": m1["id"], "decision": "clip", "confidence": 0.85, "start_t": a, "end_t": b,
                                                        "screen_title": "REAÇÃO NA LIVE", "title": "Olha essa reação", "reason": f"pico em t={m1['peak']:.0f}s",
                                                        "summary": "Reação forte do streamer."})]))[0]
    assert not ok["error"] and json.loads(ok["text"])["status"] == "clip_requested", ok["text"]
    if len(cands) > 1:
        sk = asyncio.run(mcp(base, tok, [("review_moment", {"moment_id": cands[1]["id"], "decision": "skip", "confidence": 0.7, "reason": "sem gatilho"})]))[0]
        assert not sk["error"] and json.loads(sk["text"])["status"] == "rejected"
    again = asyncio.run(mcp(base, tok, [("review_moment", {"moment_id": m1["id"], "decision": "skip", "confidence": 0.5, "reason": "x"})]))[0]
    assert again["error"]  # já decidido: não muda de novo
    clip_id = wait(lambda: json.loads(asyncio.run(mcp(base, tok, [("get_highlight", {"moment_id": m1["id"], "include_frames": False})]))[0]["text"]).get("clip")
                   and json.loads(asyncio.run(mcp(base, tok, [("get_highlight", {"moment_id": m1["id"], "include_frames": False})]))[0]["text"])["clip"]["clip_id"],
                   240, 4, msg="corte criado")
    wait(lambda: '"ready"' in asyncio.run(mcp(base, tok, [("get_render_status", {"clip_id": clip_id})]))[0]["text"], 300, 5, msg="render")
    ap = asyncio.run(mcp(base, tok, [("approve_clip", {"clip_id": clip_id})]))[0]; assert '"approved"' in ap["text"]
    v = u.get(f"/api/clips/{clip_id}/video"); p = st["data"] / "c.mp4"; p.write_bytes(v.content)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)
    assert abs(dur - (b - a)) < 0.7, (dur, a, b)  # o corte tem exatamente o intervalo decidido pelo Claude do cliente
    cp = u.get(f"/api/projects/{u.get(f'/api/live/sessions/{sid}').json()['project_id']}").json()["items"][0]["copy"]
    assert cp["screen_title"] == "REAÇÃO NA LIVE"
    # a linha do tempo mostra o que foi mostrado ao Claude e a decisão dele, marcada como via MCP
    db = sqlite3.connect(st["data"] / "app.db"); kinds = [r[0] for r in db.execute("SELECT kind FROM live_events WHERE session_id=?", (sid,))]
    assert "frames_shared" in kinds
    an = [json.loads(r[0]) for r in db.execute("SELECT data FROM live_events WHERE session_id=? AND kind='analysis'", (sid,))]
    assert an and an[0]["via"] == "mcp" and an[0]["client"] == "Claude"
    assert db.execute("SELECT SUM(spent_usd), SUM(calls) FROM live_sessions").fetchone() == (0.0, 0)  # nenhuma chamada de API no servidor
    asyncio.run(mcp(base, tok, [("stop_monitoring", {"stream_id": stream_id})]))
    wait(lambda: u.get(f"/api/live/sessions/{sid}").json()["status"] == "stopped", 120, msg="parar")
