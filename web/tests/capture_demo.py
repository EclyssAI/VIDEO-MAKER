"""Captura as demonstrações REAIS do app usadas na landing (web/static/site/media/).
Sobe web + worker + agente com fonte de teste (LIVE_SOURCE_OVERRIDE = pasta com trechos de "Tears of Steel", CC BY 3.0),
conecta 3 transmissões, processa um upload do mesmo filme pelo motor, chama o MCP de verdade e fotografa as telas.
Uso: python -m web.tests.capture_demo --fixtures <pasta> --upload <video.mp4> --out web/static/site/media
O app mostra "Fonte de teste" nas telas capturadas; a landing informa a origem do conteúdo na legenda."""
import argparse, asyncio, json, os, pathlib, signal, socket, sqlite3, subprocess, sys, tempfile, time
import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
H = {"x-vm": "1"}


def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


async def mcp_list(base, token):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60) as hc:
        async with Client(streamable_http_client(base + "/mcp", http_client=hc)) as cl:
            r = await cl.call_tool("list_connected_streamers", {})
            return "".join(getattr(c, "text", "") for c in r.content)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fixtures", required=True); ap.add_argument("--upload", required=True)
    ap.add_argument("--out", default=str(ROOT / "web/static/site/media")); ap.add_argument("--wait", type=float, default=75)
    ap.add_argument("--plan", default="creator", choices=["creator", "studio"]); ap.add_argument("--streams", type=int, default=3)
    ap.add_argument("--shot", default="monitor.webp", help="nome do arquivo da captura da grade")
    a = ap.parse_args(); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    data = pathlib.Path(tempfile.mkdtemp(prefix="vm-demo-")); p = port(); base = f"http://127.0.0.1:{p}"
    env = {**os.environ, "VM_DATA_DIR": str(data), "BETA_SIGNUP": "0", "COOKIE_SECURE": "0", "PUBLIC_URL": base, "LIVE_MAX_SESSIONS": "10",
           "LIVE_SOURCE_OVERRIDE": str(pathlib.Path(a.fixtures).resolve()), "LIVE_AUDIO_DB": "6"}
    env.pop("ANTHROPIC_API_KEY", None)
    for k in ("NO_PROXY", "no_proxy"): env[k] = env.get(k, "") + ",127.0.0.1"
    log = lambda n: open(data / f"{n}.log", "w")
    procs = [subprocess.Popen([sys.executable, "-m", "uvicorn", "web.app:app", "--port", str(p)], cwd=ROOT, env=env, stdout=log("web"), stderr=subprocess.STDOUT),
             subprocess.Popen([sys.executable, "-m", "web.worker"], cwd=ROOT, env=env, stdout=log("worker"), stderr=subprocess.STDOUT),
             subprocess.Popen([sys.executable, "-m", "web.live.agent"], cwd=ROOT, env=env, stdout=log("agent"), stderr=subprocess.STDOUT)]
    try:
        for _ in range(60):
            try:
                if httpx.get(base + "/healthz").status_code == 200: break
            except httpx.HTTPError: time.sleep(0.5)
        c = httpx.Client(base_url=base, timeout=120)
        assert c.post("/api/auth/signup", json={"email": "demo@clipeiaki.test", "password": "senha-forte-123", "name": "Demo", "accept_terms": True}, headers=H).status_code == 200
        db = sqlite3.connect(data / "app.db", isolation_level=None)
        db.execute("UPDATE users SET plan=?, plan_status='active', plan_until=?, email_verified=1, handle='@clipeiaki'", (a.plan, time.time() + 30 * 86400))
        for ch in [f"demo_canal_{x}" for x in "abcdefghij"][:a.streams]:
            sid = c.post("/api/live/streams", json={"channel": ch, "rights_basis": "owner"}, headers=H).json()["id"]
            assert c.post(f"/api/live/streams/{sid}/start", json={"budget_usd": 0, "max_minutes": 20}, headers=H).status_code == 200
        pid = c.post("/api/projects", json={"name": "Tears of Steel · trecho (CC BY)", "filename": "trecho.mp4", "size": os.path.getsize(a.upload), "lang": "en"}, headers=H).json()["id"]
        with open(a.upload, "rb") as f: assert c.put(f"/api/projects/{pid}/source", content=f.read(), headers=H).status_code == 200
        t0 = time.time()
        while time.time() - t0 < 600:
            pr = c.get(f"/api/projects/{pid}").json()
            if pr["items"] and any(x["status"] == "ready" for x in pr["items"]) and time.time() - t0 > a.wait: break
            time.sleep(5)
        mon = c.get("/api/live/monitor").json()
        print("monitor:", [(s["channel"], s["state"], s["session"] and s["session"]["candidates"]) for s in mon["streams"]])
        tok = c.post("/api/tokens", json={"name": "Claude Code (demo)", "scopes": ["live:read"], "days": 30}, headers=H).json()["token"]
        mcp_txt = asyncio.run(mcp_list(base, tok)); (out / "mcp_list_connected_streamers.json").write_text(mcp_txt)
        clip = next(x for x in pr["items"] if x["status"] == "ready")
        cookie = c.cookies.get("vm_session")
        r = subprocess.run(["node", str(ROOT / "web/tests/capture_shots.js")], cwd=ROOT, text=True, capture_output=True,
                           env={**os.environ, "BASE": base, "COOKIE": cookie, "SHOT": a.shot, "PID": pid, "OUT": str(out), "MCP": str(out / "mcp_list_connected_streamers.json")})
        print(r.stdout[-2000:], r.stderr[-2000:])
        # quadros antes/depois e vídeo curto de exemplo (saída real do motor)
        v = c.get(f"/api/clips/{clip['id']}/video"); (data / "clip.mp4").write_bytes(v.content)
        mid = clip["start"] + (clip["end"] - clip["start"]) / 2
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", a.upload, "-frames:v", "1", "-vf", "scale=1280:-2", str(data / "antes.png")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(clip['end'] - clip['start']) / 2:.2f}", "-i", str(data / "clip.mp4"), "-frames:v", "1", "-vf", "scale=540:-2", str(data / "depois.png")], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(data / "clip.mp4"), "-t", "15", "-vf", "scale=540:-2", "-c:v", "libx264", "-preset", "slow", "-crf", "28",
                        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out / "exemplo.mp4")], check=True)
        from PIL import Image
        for n in ("antes", "depois"): Image.open(data / f"{n}.png").save(out / f"{n}.webp", "WEBP", quality=82)
        json.dump({"clip": clip, "monitor": mon, "data_dir": str(data)}, open(out.parent / "demo_capture_meta.json", "w"), ensure_ascii=False, default=str, indent=1)
        print("ok", out)
    finally:
        for pr_ in procs: pr_.send_signal(signal.SIGTERM)
        for pr_ in procs:
            try: pr_.wait(30)
            except subprocess.TimeoutExpired: pr_.kill()


if __name__ == "__main__": main()
