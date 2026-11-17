"""Loop da madrugada: grava 30 min de cada live online -> detecta momentos -> renderiza -> recomeça.
A gravação do próximo ciclo começa enquanto o anterior é processado (sem buracos).
Emite 'BATCH_READY <dir> clips=N aguardando_copy=M' (o Claude acorda, escreve copy.json em lote e renderiza).
Uso: nohup python live/cycle.py > logs/cycle.log 2>&1 &"""
import subprocess, threading, datetime, time, pathlib, json, sys, yaml
R = pathlib.Path(__file__).resolve().parent.parent; PY = sys.executable

def in_quiet_hours(c):
    if "--always" in sys.argv: return True
    a, b = c["quiet_hours"]; now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime("%H:%M")
    return a <= now < b if a < b else (now >= a or now < b)

def record(st, batch, mins):
    return subprocess.Popen(["streamlink", "--twitch-disable-ads", "--hls-duration", f"{mins}:00", "-o", str(batch/f"{st['name']}.ts"),
                             "--force", st["url"], "best"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def process(batch):
    subprocess.run([PY, str(R/"live/detect.py"), str(batch)])
    subprocess.run([PY, str(R/"live/render_live.py"), str(batch)])
    clips = json.loads((batch/"pending.json").read_text()) if (batch/"pending.json").exists() else []
    print(f"BATCH_READY {batch} clips={len(clips)} aguardando_copy={sum(c['lang']!='pt' for c in clips)}", flush=True)

while True:
    c = yaml.safe_load((R/"config/live.yaml").read_text())
    if not in_quiet_hours(c): time.sleep(300); continue
    batch = R/"work/live"/datetime.datetime.now().strftime("%Y%m%d_%H%M"); batch.mkdir(parents=True, exist_ok=True)
    procs = [record(s, batch, c["cycle_minutes"]) for s in c["streamers"]]
    for p in procs: p.wait()
    if not any(f.stat().st_size > 1e6 for f in batch.glob("*.ts")):
        print(f"[offline] nenhuma live em {batch.name}", flush=True); time.sleep(120); continue
    threading.Thread(target=process, args=(batch,), daemon=True).start()
