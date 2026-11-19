"""Teste de carga do Live Monitor (não é pytest: mede e grava um relatório JSON).

  [REAL]    python -m web.tests.load_live --mode real --streams 3 --minutes 8 --out docs/evidencias/carga_real_3.json
  [FIXTURE] python -m web.tests.load_live --mode fixture --source /dir/vod.mp4 --streams 10 --minutes 5 --out ...

REAL = canais da Twitch ao vivo de verdade (escolhidos entre os que estão ao vivo agora).
FIXTURE = um arquivo de vídeo real tocado em tempo real como se fosse live (LIVE_SOURCE_OVERRIDE): mesma CPU de
decodificação/análise, SEM rede e sem a variação de uma live. Os dois tipos de evidência nunca são misturados no relatório.

Mede, por amostragem a cada 5 s: CPU (núcleos) e RSS da árvore de processos do agente (python + streamlink + ffmpeg),
CPU da máquina, banda de entrada (bytes dos blocos .ts gravados / tempo), disco temporário (buffer de blocos),
minutos efetivamente analisados, atraso entre a gravação e o processamento (lag), latência de detecção (evento na
live → candidato registrado), fila de render, tempo de render de cortes solicitados durante a carga e recuperação
após SIGKILL do agente. Claude: só é chamado se ANTHROPIC_API_KEY existir (por padrão, não existe → custo 0)."""
import argparse, json, os, pathlib, signal, socket, sqlite3, statistics, subprocess, sys, tempfile, time
import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
H = {"x-vm": "1"}
TICK = os.sysconf("SC_CLK_TCK")
CANDIDATES = ["kaicenat", "xqc", "ibai", "gaules", "casimiro", "loud_coringa", "tarik", "shroud", "summit1g", "hasanabi", "jynxzi",
              "caseoh_", "zackrawrr", "pokimane", "auronplay", "elmariana", "fps_shaka", "kamet0", "squeezie", "tumblurr", "sodapoppin",
              "lirik", "timthetatman", "moistcr1tikal", "trainwreckstv", "stableronaldo", "fanum", "plaqueboymax", "yourragegaming",
              "jasontheween", "elspreen", "rubius", "illojuan", "alanzoka", "baiano", "cellbit", "mch_agg", "ninja", "nickmercs"]


def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def proc_stat(pid):
    try:
        f = pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        rss = int(pathlib.Path(f"/proc/{pid}/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        return {"ppid": int(f[1]), "cpu": (int(f[11]) + int(f[12])) / TICK, "ccpu": (int(f[13]) + int(f[14])) / TICK, "rss": rss}
    except (OSError, IndexError, ValueError):
        return None


def tree(root):
    """CPU acumulada (s) e RSS (bytes) do processo + descendentes vivos. Filhos que já terminaram entram no cutime do pai."""
    procs = {}
    for d in pathlib.Path("/proc").iterdir():
        if d.name.isdigit():
            s = proc_stat(int(d.name))
            if s: procs[int(d.name)] = s
    ids, frontier = {root}, [root]
    while frontier:
        p = frontier.pop(); kids = [k for k, v in procs.items() if v["ppid"] == p and k not in ids]; ids.update(kids); frontier += kids
    cpu = sum(procs[i]["cpu"] for i in ids if i in procs) + (procs[root]["ccpu"] if root in procs else 0)
    return cpu, sum(procs[i]["rss"] for i in ids if i in procs), len(ids)


def machine_cpu():
    v = list(map(int, pathlib.Path("/proc/stat").read_text().split("\n")[0].split()[1:]))
    return sum(v), v[3] + v[4]  # total, idle+iowait


def du(path):
    return sum(f.stat().st_size for f in pathlib.Path(path).rglob("*") if f.is_file()) if pathlib.Path(path).exists() else 0


def live_channels(n):
    sys.path.insert(0, str(ROOT)); from web.live import service
    out = []
    for ch in CANDIDATES:
        try: st = service._query(ch)
        except Exception: continue
        if st.get("live") and any(q in st.get("qualities", []) for q in ("720p60", "720p", "480p")):
            out.append({"channel": ch, "title": st.get("title"), "category": st.get("category")})
            print(f"  ao vivo: {ch} · {st.get('category')}", flush=True)
            if len(out) >= n: break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["real", "fixture"], required=True); ap.add_argument("--streams", type=int, default=3)
    ap.add_argument("--minutes", type=float, default=6); ap.add_argument("--source"); ap.add_argument("--out", required=True)
    ap.add_argument("--kill-at", type=float, default=0.5, help="fração da duração em que o agente leva SIGKILL (0 = não testa)")
    ap.add_argument("--clips", type=int, default=1, help="cortes solicitados por transmissão durante a carga")
    ap.add_argument("--transcribe", default="events", choices=["events", "all"])
    a = ap.parse_args()
    data = pathlib.Path(tempfile.mkdtemp(prefix=f"vm-load-{a.mode}-{a.streams}-")); p = port(); base = f"http://127.0.0.1:{p}"
    env = {**os.environ, "VM_DATA_DIR": str(data), "BETA_SIGNUP": "0", "COOKIE_SECURE": "0", "PUBLIC_URL": base, "LIVE_MAX_SESSIONS": str(a.streams),
           "LIVE_CAPACITY_TOTAL": str(a.streams), "LIVE_TRANSCRIBE": a.transcribe, "LIVE_LEASE_S": "20", "SIGNUP_PER_IP_HOUR": "100"}
    for k in ("NO_PROXY", "no_proxy"): env[k] = env.get(k, "") + ",127.0.0.1"
    if a.mode == "fixture":
        env["LIVE_SOURCE_OVERRIDE"] = str(pathlib.Path(a.source).resolve())
        channels = [{"channel": f"fixture_{k}", "title": pathlib.Path(a.source).name, "category": "FIXTURE"} for k in range(a.streams)]
    else:
        print("procurando canais ao vivo…", flush=True); channels = live_channels(a.streams)
        if len(channels) < a.streams: sys.exit(f"só {len(channels)} canais ao vivo encontrados")
    log = lambda name: open(data / f"{name}.log", "a")
    procs = {"web": subprocess.Popen([sys.executable, "-m", "uvicorn", "web.app:app", "--port", str(p)], cwd=ROOT, env=env, stdout=log("web"), stderr=subprocess.STDOUT),
             "worker": subprocess.Popen(["nice", "-n", "10", sys.executable, "-m", "web.worker"], cwd=ROOT, env=env, stdout=log("worker"), stderr=subprocess.STDOUT)}
    start_agent = lambda: subprocess.Popen([sys.executable, "-m", "web.live.agent"], cwd=ROOT, env=env, stdout=log("agent"), stderr=subprocess.STDOUT)
    procs["agent"] = start_agent()
    for _ in range(60):
        try:
            if httpx.get(base + "/healthz").status_code == 200: break
        except httpx.HTTPError: time.sleep(0.5)
    c = httpx.Client(base_url=base, timeout=60)
    assert c.post("/api/auth/signup", json={"email": "carga@teste.com", "password": "senha-forte-123", "accept_terms": True}, headers=H).status_code == 200
    db = sqlite3.connect(data / "app.db", isolation_level=None, timeout=30); db.row_factory = sqlite3.Row
    db.execute("UPDATE users SET plan='studio', plan_status='active', plan_until=?, email_verified=1", (time.time() + 86400 * 30,))
    sids = []
    for ch in channels:
        st = c.post("/api/live/streams", json={"channel": ch["channel"], "rights_basis": "authorized"}, headers=H); assert st.status_code == 200, st.text
        r = c.post(f"/api/live/streams/{st.json()['id']}/start", json={"budget_usd": 0, "max_minutes": a.minutes + 10}, headers=H)
        assert r.status_code == 200, r.text; sids.append(r.json()["id"])
    t0 = time.time(); dur = a.minutes * 60; samples = []; killed = None; restarted = None; requested = set()
    cpu_prev = None; m_prev = machine_cpu(); print(f"{a.streams} sessões iniciadas ({a.mode}); medindo por {a.minutes} min", flush=True)
    while time.time() - t0 < dur:
        time.sleep(5); now = time.time()
        cpu, rss, nproc = tree(procs["agent"].pid) if procs["agent"].poll() is None else (0, 0, 0)
        mt, mi = machine_cpu(); mach = 1 - (mi - m_prev[1]) / max(1, mt - m_prev[0]); m_prev = (mt, mi)
        cores = (cpu - cpu_prev[0]) / (now - cpu_prev[1]) if cpu_prev and cpu >= cpu_prev[0] else None; cpu_prev = (cpu, now)
        q = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
        st = db.execute("SELECT status, COUNT(*) n FROM live_sessions GROUP BY status").fetchall()
        samples.append({"t": round(now - t0, 1), "agent_cores": round(cores, 3) if cores is not None else None, "agent_rss_mb": round(rss / 2**20, 1),
                        "agent_procs": nproc, "machine_cpu_pct": round(mach * 100, 1), "render_queue": q, "buffer_mb": round(du(data / "users") / 2**20, 1),
                        "sessions": {r["status"]: r["n"] for r in st}})
        print(json.dumps(samples[-1]), flush=True)
        # cortes durante a carga: o primeiro candidato de cada sessão vira corte (simula o usuário aprovando um candidato)
        for sid in sids:
            if sum(1 for x in requested if x[0] == sid) >= a.clips: continue
            m = db.execute("SELECT id FROM live_moments WHERE session_id=? AND status='candidate' AND clip_id='' ORDER BY peak LIMIT 1", (sid,)).fetchone()
            if m and c.post(f"/api/live/sessions/{sid}/clips", json={"moment_id": m["id"]}, headers=H).status_code == 200:
                requested.add((sid, m["id"]))
        if a.kill_at and not killed and now - t0 >= dur * a.kill_at:
            procs["agent"].send_signal(signal.SIGKILL); procs["agent"].wait(); killed = time.time(); print("SIGKILL no agente", flush=True)
            time.sleep(3); procs["agent"] = start_agent(); restarted = time.time(); cpu_prev = None
    for sid in sids: c.post(f"/api/live/sessions/{sid}/stop", headers=H)
    for _ in range(90):
        if db.execute("SELECT COUNT(*) FROM live_sessions WHERE status!='stopped'").fetchone()[0] == 0: break
        time.sleep(2)
    for _ in range(120):  # espera os renders pedidos durante a carga
        if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] == 0: break
        time.sleep(2)
    ev = lambda kind: [{**dict(r), "data": json.loads(r["data"])} for r in db.execute("SELECT * FROM live_events WHERE kind=? ORDER BY id", (kind,))]
    segs = [dict(r) for r in db.execute("SELECT session_id, seq, t_start, duration, wall_start, transcribed, path FROM live_segments WHERE duration>0")]
    seg_ev = ev("segment"); cand = ev("candidate"); ready = ev("clip_ready"); failed = ev("clip_failed"); resumed = ev("resumed")
    per = {}
    for sid in sids:
        ss = sorted([x for x in segs if x["session_id"] == sid], key=lambda x: x["seq"])
        gaps = [round(b["t_start"] - (x["t_start"] + x["duration"]), 2) for x, b in zip(ss, ss[1:]) if abs(b["t_start"] - (x["t_start"] + x["duration"])) > 0.06]
        ses = db.execute("SELECT * FROM live_sessions WHERE id=?", (sid,)).fetchone()
        per[sid] = {"channel": ses["channel"], "recorded_s": round(ses["recorded_s"], 1), "segments": len(ss), "gaps_s": gaps,
                    "transcribed_segments": sum(x["transcribed"] for x in ss), "candidates": sum(1 for e in cand if e["session_id"] == sid),
                    "stop_reason": ses["stop_reason"]}
    lag = [e["data"]["lag_s"] for e in seg_ev]
    det = [round(e["wall_at"] - e["data"]["wall_at"], 1) for e in cand if e["data"].get("wall_at")]
    after = [x for x in samples if x["agent_cores"] is not None and x["t"] > 30]
    total_rec = sum(v["recorded_s"] for v in per.values())
    report = {
        "evidence_type": "REAL (Twitch ao vivo)" if a.mode == "real" else "FIXTURE (arquivo local tocado como live; sem rede)",
        "streams": a.streams, "minutes": a.minutes, "transcribe_mode": a.transcribe, "channels": channels,
        "machine": {"cpus": os.cpu_count(), "mem_gb": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)},
        "cpu_cores_agent": {"mean": round(statistics.mean(x["agent_cores"] for x in after), 2) if after else None,
                            "p95": round(sorted(x["agent_cores"] for x in after)[int(len(after) * .95) - 1], 2) if after else None},
        "cpu_cores_per_stream": round(statistics.mean(x["agent_cores"] for x in after) / a.streams, 3) if after else None,
        "machine_cpu_pct_mean": round(statistics.mean(x["machine_cpu_pct"] for x in after), 1) if after else None,
        "rss_mb_agent": {"mean": round(statistics.mean(x["agent_rss_mb"] for x in after), 1) if after else None,
                         "max": max((x["agent_rss_mb"] for x in samples), default=None)},
        "buffer_mb_max": max((x["buffer_mb"] for x in samples), default=0),
        "recorded_minutes_total": round(total_rec / 60, 1), "analyzed_minutes_total": round(total_rec / 60, 1),
        "transcribed_fraction": round(sum(v["transcribed_segments"] for v in per.values()) / max(1, sum(v["segments"] for v in per.values())), 3),
        "processing_lag_s": {"p50": round(statistics.median(lag), 1) if lag else None, "p95": round(sorted(lag)[int(len(lag) * .95) - 1], 1) if lag else None,
                             "max": max(lag) if lag else None},
        "detection_latency_s": {"p50": statistics.median(det) if det else None, "max": max(det) if det else None, "n": len(det)},
        "render": {"requested": len(requested), "ready": len(ready), "failed": len(failed),
                   "render_s": [e["data"]["render_s"] for e in ready], "render_queue_max": max((x["render_queue"] for x in samples), default=0)},
        "recovery": {"killed_at_s": round(killed - t0, 1) if killed else None,
                     "resumed_sessions": len({e["session_id"] for e in resumed}),
                     "resume_after_kill_s": sorted(round(e["wall_at"] - killed, 1) for e in resumed) if killed else [],
                     "gaps_after_recovery": {k: v["gaps_s"] for k, v in per.items() if v["gaps_s"]}},
        "claude": {"configured": bool(os.environ.get("ANTHROPIC_API_KEY")), "calls": sum(r["calls"] for r in db.execute("SELECT calls FROM live_sessions")),
                   "spent_usd": round(sum(r["spent_usd"] for r in db.execute("SELECT spent_usd FROM live_sessions")), 4)},
        "candidates_per_stream_hour": round(len(cand) / max(1e-9, total_rec / 3600), 1),
        "sessions": per, "samples": samples}
    # banda de entrada medida: bytes de cada bloco .ts gravado (registrado pelo agente no evento "segment") / duração do bloco
    b = sum(e["data"].get("bytes", 0) for e in seg_ev); d = sum(e["data"]["duration"] for e in seg_ev)
    report["input_mbps_per_stream"] = round(b * 8 / max(1e-9, d) / 1e6, 2)
    report["input_mbps_total"] = round(report["input_mbps_per_stream"] * a.streams, 1)
    report["input_gb_per_stream_hour"] = round(b / max(1e-9, d) * 3600 / 1e9, 2)
    pathlib.Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({k: v for k, v in report.items() if k not in ("samples", "sessions")}, indent=1, ensure_ascii=False, default=str))
    for pr in procs.values():
        if pr.poll() is None: pr.send_signal(signal.SIGTERM)
    for pr in procs.values():
        try: pr.wait(30)
        except subprocess.TimeoutExpired: pr.kill()


if __name__ == "__main__": main()
