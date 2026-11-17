"""render: work/<id>/edit.json -> output/<data>_<slug>/{video.mp4,meta.json,descricao.txt}
edit.json (gerado pelo Claude após /viralizei):
 {id, title, hook, description, hashtags[], start, end, captions:[{start,end,text}]}
Layout ClipeiAki 9:16: fundo desfocado + vídeo centralizado + barra de hook + legenda + watermark."""
import json, sys, re, subprocess, pathlib, datetime, yaml
ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT/"config/channel.yaml").read_text())

def bgr(h): return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&"
def ts(t):
    h, m, s = int(t//3600), int(t%3600//60), t%60
    return f"{h}:{m:02d}:{s:05.2f}"

def ass(caps, hook, dur):
    b, c = CFG["brand"], CFG["captions"]; W, H = CFG["format"]["width"], CFG["format"]["height"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,{b['font']},{c['font_size']},{bgr(b['text'])},&H000000FF,{bgr(b['outline'])},&H80000000,-1,0,0,0,100,100,0,0,1,7,2,2,60,60,{c['margin_bottom']},1
Style: Hook,{b['font']},72,{bgr(b['text'])},&H000000FF,{bgr(b['outline'])},&H00000000,-1,0,0,0,100,100,0,0,1,5,0,8,60,60,330,1
Style: Wm,{b['font']},46,{bgr(b['accent'])},&H000000FF,{bgr(b['outline'])},&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,300,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    ev = []
    for x in caps:
        t = x["text"].upper() if c["uppercase"] else x["text"]
        ev.append(f"Dialogue: 1,{ts(x['start'])},{ts(x['end'])},Cap,,0,0,0,,{{\\fad(40,0)\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}}{t}")
    if hook: ev.append(f"Dialogue: 2,{ts(0)},{ts(min(3.0,dur))},Hook,,0,0,0,,{{\\fad(0,250)}}{hook.upper()}")
    ev.append(f"Dialogue: 0,{ts(0)},{ts(dur)},Wm,,0,0,0,,{b['watermark']}")
    return head + "\n".join(ev) + "\n"

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower().encode("ascii", "ignore").decode()).strip("-")[:40] or "clip"

def render(e):
    wd = ROOT/"work"/e["id"]; seg = json.loads((wd/"segments.json").read_text())
    dur = e["end"] - e["start"]; W, H = CFG["format"]["width"], CFG["format"]["height"]
    (wd/"cap.ass").write_text(ass([{**x, "start": x["start"]-e["start"], "end": x["end"]-e["start"]} for x in e["captions"]], e.get("hook"), dur))
    out = ROOT/"output"/f"{datetime.date.today():%Y%m%d}_{slug(e['title'])}"; out.mkdir(parents=True, exist_ok=True)
    fg_h = int(W*9/16) if e.get("source_aspect","16:9") == "16:9" else 1280
    vf = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:5,eq=brightness=-0.15[bg];"
          f"[b]scale={W}:-2:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,"
          f"ass={wd/'cap.ass'}[v]")
    subprocess.run(["ffmpeg","-y","-v","error","-ss",str(e["start"]),"-t",str(dur),"-i",seg["video"],
        "-filter_complex",vf,"-map","[v]","-map","0:a?","-r",str(CFG["format"]["fps"]),
        "-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-b:a","160k",
        "-movflags","+faststart",str(out/"video.mp4")],check=True)
    tags = " ".join(dict.fromkeys(e.get("hashtags", []) + CFG["hashtags_base"]))
    desc = f"{e['description']}\n\n{('Créditos: '+seg['credit']+chr(10)) if seg.get('credit') and CFG['credit_in_description'] else ''}Segue o {CFG['handle']} 🔔\n\n{tags}"
    (out/"descricao.txt").write_text(f"TÍTULO: {e['title']}\n\nDESCRIÇÃO:\n{desc}\n")
    (out/"meta.json").write_text(json.dumps({"title": e["title"], "description": desc, "hashtags": tags.split(),
        "source": seg["source"], "kind": seg["kind"], "viralizei_score": e.get("score")}, ensure_ascii=False, indent=1))
    print("[ok]", out)

if __name__ == "__main__":
    for p in sys.argv[1:]: render(json.loads(pathlib.Path(p).read_text()))
