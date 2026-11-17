"""Gera máscaras arredondadas e SFX sintetizados (sem licença) uma vez."""
import subprocess, pathlib, yaml
from PIL import Image, ImageDraw
R = pathlib.Path(__file__).resolve().parent.parent; L = yaml.safe_load((R/"config/live.yaml").read_text())["layout"]
for k in ("cam", "game_cam", "game_full"):
    x, y, w, h = L[k]; m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w-1, h-1], L["radius"], fill=255); m.save(R/f"template/assets/mask_{k}.png")
S = R/"template/sfx"; sfx = {
 "impact": "aevalsrc='0.9*sin(2*PI*(55+80*exp(-12*t))*t)*exp(-5*t)+0.3*(random(0)*2-1)*exp(-25*t)':d=0.9",
 "whoosh": "anoisesrc=d=0.6:c=pink,bandpass=f=1800:w=1500,afade=t=in:d=0.35,afade=t=out:st=0.35:d=0.25",
 "riser":  "aevalsrc='0.4*sin(2*PI*(200+900*t*t)*t)':d=1.2,afade=t=in:d=1",
 "pop":    "aevalsrc='0.7*sin(2*PI*900*t)*exp(-30*t)':d=0.25"}
for n, f in sfx.items():
    subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",f,"-ac","2","-ar","48000",str(S/f"{n}.wav")], check=True)
print("assets ok")
