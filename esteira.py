"""ESTEIRA ClipeiAki — captar -> cortar -> template/título/legenda -> aprovar -> postar (TikTok, Reels, Shorts).
  python esteira.py scrap                 # virais dos perfis gringos (clone ViceScrap/ViceRepost)
  python esteira.py live [--always]       # lives em ciclos de 30 min (madrugada), roda em loop
  python esteira.py add <arquivo|link>... # qualquer vídeo/VOD: vira vários cortes
  python esteira.py cut <lote>            # detecta momentos + transcreve -> for_claude.txt
  python esteira.py render <lote>         # aplica template (usa copy.json do /viralizei)
  python esteira.py approve <lote> 1 3    # agenda nos horários de pico
  python esteira.py post [--now] | status"""
import sys, subprocess, pathlib, datetime, json
R = pathlib.Path(__file__).resolve().parent; PY = sys.executable; a = sys.argv[1:]
def sh(*x): subprocess.run([PY, *map(str, x)], check=True)
def lote(n): return R/"work/batch"/n
if not a: print(__doc__)
elif a[0] == "scrap":
    sh(R/"capture/scrap.py"); b = sorted((R/"work/batch").glob("*_scrap"))[-1]; sh(R/"live/detect.py", b); print("LOTE", b.name)
elif a[0] == "live": subprocess.run([PY, R/"live/cycle.py", *a[1:]])
elif a[0] == "add":
    b = lote(datetime.datetime.now().strftime("%Y%m%d_%H%M") + "_add"); b.mkdir(parents=True, exist_ok=True); meta = {}
    for i, s in enumerate(a[1:]):
        n = f"add{i:02d}"; p = pathlib.Path(s)
        if p.exists(): (b/f"{n}{p.suffix}").symlink_to(p.resolve())
        else: subprocess.run(["yt-dlp", "-q", "-f", "mp4/best", "-o", str(b/f"{n}.mp4"), s], check=True)
        meta[n] = {"lang": "en", "webcam": None, "credit": s, "kind": "meme"}
    (b/"sources.json").write_text(json.dumps(meta, indent=1)); sh(R/"live/detect.py", b); print("LOTE", b.name)
elif a[0] == "cut": sh(R/"live/detect.py", lote(a[1]))
elif a[0] == "render": sh(R/"live/render_live.py", lote(a[1]))
elif a[0] in ("approve", "post", "status"): sh(R/"publish/scheduler.py", *a)
