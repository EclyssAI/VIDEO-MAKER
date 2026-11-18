"""Junta os vídeos prontos em output/ENTREGA_<data>/ com NN_slug.mp4 + NN_slug.txt (título/descrição) + LISTA.md."""
import json, pathlib, shutil, subprocess, sys, datetime
R = pathlib.Path(__file__).resolve().parent.parent
dirs = [pathlib.Path(p) for p in sys.argv[1:]]
E = R/"output"/f"ENTREGA_{datetime.date.today():%Y%m%d}"; E.mkdir(exist_ok=True); rows, descs = [], []
for n, d in enumerate(dirs, 1):
    m = json.loads((d/"meta.json").read_text()); dur = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(d/"video.mp4")],capture_output=True,text=True).stdout)
    name = f"{n:02d}_{d.name[3:]}"; shutil.copy(d/"video.mp4", E/f"{name}.mp4"); shutil.copy(d/"descricao.txt", E/f"{name}.txt")
    rows.append(f"| {n:02d} | {m['title']} | {dur:.0f}s | {'✅' if dur > 60 else '⚠️ <60s (Shorts/Reels)'} | {m.get('streamer','')} |")
    descs.append(f"## {n:02d} — {m['title']}\n\n{m['description']}\n")
(E/"LISTA.md").write_text("# Entrega ClipeiAki\n\n| # | Título | Duração | TikTok Rewards (>60s) | Créditos |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n---\n\n# Títulos e descrições (copiar e colar)\n\n" + "\n".join(descs))
print(E); print("\n".join(rows))
