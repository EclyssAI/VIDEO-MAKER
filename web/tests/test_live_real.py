"""[REAL] Claude Live Agent contra uma transmissão AO VIVO de verdade na Twitch.
Nada é simulado: gravação real (streamlink), transcrição real (Whisper), detecção real, render real (motor do João).
A análise do Claude só é real se ANTHROPIC_API_KEY estiver no ambiente; sem ela o teste exige que o sistema mostre
a integração como DESCONECTADA (sem frames enviados) e cria o corte manualmente a partir de um candidato.
Rodar: LIVE_REAL=1 [LIVE_TEST_CHANNEL=canal] [LIVE_REAL_MINUTES=4] [VM_TEST_REPORT=arquivo.json] pytest -v web/tests/test_live_real.py"""
import json, os, pathlib, signal, socket, sqlite3, statistics, subprocess, sys, tempfile, time
import httpx, pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.environ.get("LIVE_REAL") != "1", reason="defina LIVE_REAL=1 (usa rede e uma live real)")
H = {"x-vm": "1"}
CANDIDATES = ["xqc", "kaicenat", "jynxzi", "caseoh_", "zackrawrr", "summit1g", "shroud", "tarik", "hasanabi", "loud_coringa", "gaules"]


def live_channel():
    sys.path.insert(0, str(ROOT))
    from web.live.service import channel_status
    for ch in ([os.environ["LIVE_TEST_CHANNEL"]] if os.environ.get("LIVE_TEST_CHANNEL") else CANDIDATES):
        st = channel_status(ch)
        if st["live"]: return st
    pytest.skip("nenhum canal da lista está ao vivo agora")


def test_real_twitch_gravacao_deteccao_corte_e_latencias():
    ch = live_channel(); data = pathlib.Path(tempfile.mkdtemp(prefix="vm-real-"))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "VM_DATA_DIR": str(data), "BETA_SIGNUP": "1", "COOKIE_SECURE": "0", "PUBLIC_URL": f"http://127.0.0.1:{port}"}
    env.pop("LIVE_SOURCE_OVERRIDE", None)
    claude_real = bool(env.get("ANTHROPIC_API_KEY"))
    procs = [subprocess.Popen([sys.executable, "-m", "uvicorn", "web.app:app", "--port", str(port)], cwd=ROOT, env=env, stdout=open(data / "web.log", "w"), stderr=subprocess.STDOUT),
             subprocess.Popen([sys.executable, "-m", "web.worker"], cwd=ROOT, env=env, stdout=open(data / "worker.log", "w"), stderr=subprocess.STDOUT),
             subprocess.Popen([sys.executable, "-m", "web.live.agent"], cwd=ROOT, env=env, stdout=open(data / "agent.log", "w"), stderr=subprocess.STDOUT)]
    base = f"http://127.0.0.1:{port}"; minutes = float(os.environ.get("LIVE_REAL_MINUTES", "4"))
    try:
        for _ in range(60):
            try:
                if httpx.get(base + "/healthz").status_code == 200: break
            except httpx.HTTPError: time.sleep(0.5)
        c = httpx.Client(base_url=base, timeout=60)
        assert c.post("/api/auth/signup", json={"email": "real@teste.com", "password": "senha-forte-123"}, headers=H).status_code == 200
        r = c.post("/api/live/sessions", json={"channel": ch["channel"], "budget_usd": 0.5, "max_minutes": minutes + 3}, headers=H)
        assert r.status_code == 200, r.text; sid = r.json()["id"]; t_start = time.time()
        assert r.json()["claude"]["configured"] is claude_real
        db = sqlite3.connect(data / "app.db"); db.row_factory = sqlite3.Row
        q = lambda sql, *a: db.execute(sql, a).fetchall()
        # grava por N minutos; no meio, pede um corte de um candidato (ou de um trecho) e confirma que a gravação segue
        clip_id = None
        while time.time() - t_start < minutes * 60:
            time.sleep(5)
            if clip_id is None and time.time() - t_start > 90:
                m = q("SELECT id FROM live_moments WHERE session_id=? AND status IN ('candidate','rejected','clip_queued','clipped') ORDER BY score DESC LIMIT 1", sid)
                if m and not claude_real:
                    rr = c.post(f"/api/live/sessions/{sid}/clips", json={"moment_id": m[0]["id"]}, headers=H)
                elif not m:
                    segs = q("SELECT t_start FROM live_segments WHERE session_id=? AND deleted=0 AND duration>0 ORDER BY seq DESC LIMIT 3", sid)
                    rr = c.post(f"/api/live/sessions/{sid}/clips", json={"start_t": segs[-1]["t_start"], "end_t": segs[-1]["t_start"] + 15}, headers=H) if segs else None
                else:
                    rr = None
                if rr is not None:
                    assert rr.status_code == 200, rr.text
                    clip_id = "requested"
        deadline = time.time() + 240
        while time.time() < deadline and not q("SELECT 1 FROM live_events WHERE session_id=? AND kind='clip_ready'", sid): time.sleep(3)
        c.post(f"/api/live/sessions/{sid}/stop", headers=H)
        for _ in range(60):
            if q("SELECT status FROM live_sessions WHERE id=?", sid)[0]["status"] == "stopped": break
            time.sleep(2)
        ev = [{**dict(e), "data": json.loads(e["data"])} for e in q("SELECT * FROM live_events WHERE session_id=? ORDER BY id", sid)]
        segs = [dict(x) for x in q("SELECT * FROM live_segments WHERE session_id=? AND duration>0 ORDER BY seq", sid)]
        kinds = [e["kind"] for e in ev]
        lags = [e["data"]["lag_s"] for e in ev if e["kind"] == "segment"]
        cands = [e for e in ev if e["kind"] == "candidate"]
        det = [round(e["wall_at"] - e["data"]["wall_at"], 1) for e in cands]
        an = [e for e in ev if e["kind"] == "analysis"]
        ready = [e for e in ev if e["kind"] == "clip_ready"]
        report = {"channel": ch, "claude_real": claude_real, "minutes": minutes, "segments": len(segs),
                  "recorded_s": round(segs[-1]["t_start"] + segs[-1]["duration"], 1) if segs else 0,
                  "segment_lag_s": {"p50": statistics.median(lags[3:] or lags), "max_after_warmup": max(lags[3:] or lags)} if lags else None,
                  "candidates": len(cands), "detection_delay_s": det, "analyses": len(an),
                  "analysis_latency_s": [e["data"]["latency_s"] for e in an], "analysis_cost_usd": round(sum(e["data"]["cost_usd"] for e in an), 5),
                  "clips_ready": [{"render_s": e["data"]["render_s"], "event_to_clip_s": e["data"]["event_to_clip_s"], "source": e["data"]["source"]} for e in ready],
                  "kinds": {k: kinds.count(k) for k in sorted(set(kinds))}, "stop_reason": q("SELECT stop_reason FROM live_sessions WHERE id=?", sid)[0][0]}
        if os.environ.get("VM_TEST_REPORT"): pathlib.Path(os.environ["VM_TEST_REPORT"]).write_text(json.dumps(report, indent=1, ensure_ascii=False))
        print(json.dumps(report, indent=1, ensure_ascii=False))
        # verificações
        assert len(segs) >= minutes * 60 / 10 * 0.7, "poucos segmentos gravados"
        for a_, b_ in zip(segs, segs[1:]): assert abs(b_["t_start"] - (a_["t_start"] + a_["duration"])) < 0.06
        assert report["segment_lag_s"]["p50"] < 20, "processamento não acompanha a live"
        assert ready, "nenhum corte ficou pronto"
        assert all(s_["deleted"] for s_ in q("SELECT deleted FROM live_segments WHERE session_id=?", sid)), "buffer não foi limpo ao encerrar"
        if claude_real: assert an and not any(k == "analysis_skipped" for k in kinds)
        else: assert not an and (not cands or "analysis_skipped" in kinds)
    finally:
        for p in procs:
            if p.poll() is None: p.send_signal(signal.SIGTERM)
        for p in procs:
            try: p.wait(20)
            except subprocess.TimeoutExpired: p.kill()
