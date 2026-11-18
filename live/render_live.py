"""Renderiza um corte no template ClipeiAki (jogo no quadro maior, streamer no menor se houver webcam).
Uso: python live/render_live.py <batch_dir>   (lê pending.json + copy.json)"""
import json, sys, re, subprocess, pathlib, random, yaml
R = pathlib.Path(__file__).resolve().parent.parent; C = yaml.safe_load((R/"config/live.yaml").read_text())
CH = yaml.safe_load((R/"config/channel.yaml").read_text()); A = R/"template/assets"; L = C["layout"]

def ts(t): return f"0:{int(t//60):02d}:{t%60:05.2f}"
def esc(s): return s.replace("{", "(").replace("}", ")")

def fit(t, max_chars=12):
    """Quebra em 2 linhas e reduz a fonte p/ caber ao lado da mascote (área ~600px)."""
    t = t.upper(); w = t.split()
    if len(t) > max_chars and len(w) > 1:
        best = min(range(1, len(w)), key=lambda i: abs(len(" ".join(w[:i])) - len(" ".join(w[i:]))))
        t = " ".join(w[:best]) + "\\N" + " ".join(w[best:])
    longest = max(len(x) for x in t.split("\\N")); scale = min(100, int(100 * max_chars / max(longest, 1)))
    return t, scale

def kara(caps, cx, cy):
    caps = sorted(caps, key=lambda c: c["s"])
    for a, b in zip(caps, caps[1:]): a["e"] = min(a["e"], b["s"])   # sem sobreposição
    """Legenda palavra-a-palavra: bloco inteiro visível, palavra falada em amarelo e maior (estilo clipadores US)."""
    ev = []
    for c in caps:
        t, sc = fit(c["t"]); lines = [l.split() for l in t.split("\\N")]; n = sum(len(l) for l in lines) or 1
        base = "\\c&H00B050F0&" if c.get("hl") else "\\c&H00FFFFFF&"; d = (c["e"] - c["s"]) / n; k = 0
        for li, line in enumerate(lines):
            for wi in range(len(line)):
                txt = "\\N".join(" ".join((f"{{\\c&H0000D4FF&\\fscx112\\fscy112}}{esc(w)}{{{base}\\fscx100\\fscy100}}" if (a, b) == (li, wi) else esc(w))
                                          for b, w in enumerate(l)) for a, l in enumerate(lines))
                pop = f"\\fscx{int(sc*.8)}\\fscy{int(sc*.8)}\\t(0,80,\\fscx{sc}\\fscy{sc})" if k == 0 else f"\\fscx{sc}\\fscy{sc}"
                ev.append(f"Dialogue: 2,{ts(c['s']+k*d)},{ts(c['s']+(k+1)*d)},C,,0,0,0,,{{\\pos({cx},{cy}){pop}{base}}}{txt}\n"); k += 1
    return "".join(ev)

def ass(path, title, caps):
    tx, ty = 540, L["title_y"]; cx, cy = L["caption_xy"]
    path.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: T,Inter,62,&H00350F13,&H000000FF,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,140,140,0,1
Style: C,Inter,74,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,0,0,0,1
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 1,0:00:00.00,9:00:00.00,T,,0,0,0,,{{\\pos({tx},{ty})\\fad(150,0)}}{esc(title.upper())}
""" + kara(caps, cx, cy))

def captions(words, per=3):
    out = []
    for i in range(0, len(words), per):
        g = words[i:i+per]; out.append({"s": g[0]["s"], "e": max(g[-1]["e"], g[0]["s"]+0.4), "t": " ".join(w["w"] for w in g)})
    return out

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower().encode("ascii", "ignore").decode()).strip("-")[:40] or "corte"

def render(c, cp, out_root, n):
    dur = c["end"]-c["start"]; cam = c["webcam"]; P = c["peak"]
    gx, gy, gw, gh = L["game_cam" if cam else "game_full"]
    out = out_root/f"{n:02d}_{slug(cp['title'])}"; out.mkdir(parents=True, exist_ok=True)
    caps = cp.get("captions") or captions(c["words"]); ass(out/"subs.ass", cp.get("screen_title", cp["title"]), caps)
    tb = c.get("trim_bottom", L.get("trim_bottom", 0)); eh = int(gh/(1-tb))  # corta legenda/HUD gravados no rodapé da live
    sw = eh*16/9  # largura do jogo escalado (fonte 16:9)
    xoff = (sw-gw)/2
    if c.get("focus") is not None and not cam:  # centraliza o streamer/ação (fração da largura da fonte)
        xoff = max(0, min(sw-gw, c["focus"]*sw - gw/2))
    if cam:  # afasta o recorte do jogo da webcam
        k = eh/1080; cx0, cx1 = cam[0]*k, (cam[0]+cam[2])*k
        xoff = max(0, min(xoff, cx0-gw)) if cam[0] > 960 else min(sw-gw, max(xoff, cx1))
    zoom = (f",zoompan=z='if(between(it,{P-0.2:.2f},{P+C['broll']['seconds']:.2f}),1.18,1)':d=1:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={gw}x{gh}:fps=30") if C["broll"]["enabled"] else ""
    inp = ["-framerate","30","-loop","1","-i",str(A/"background.png"), "-ss",str(c["start"]),"-t",str(dur),"-i",c["src"],
           "-i",str(A/("frame_webcam.png" if cam else "frame_full.png")), "-i",str(A/"logo.png"), "-i",str(A/"mascot.png"),
           "-i",str(A/f"mask_{'game_cam' if cam else 'game_full'}.png"), "-i",str(A/"mask_cam.png"),
           "-i",str(R/"template/sfx/whoosh.wav"), "-i",str(R/"template/sfx/impact.wav")]
    g = (f"[1:v]fps=30,split[gs][cs];" +
         (f"[gs]scale=-2:{eh},crop={gw}:{gh}:{xoff:.0f}:0" if (cam or c.get("focus") is not None) else f"[gs]scale={gw}:{eh}:force_original_aspect_ratio=increase,crop={gw}:{gh}:(iw-ow)/2:0") + (f",scale={int(gw*c['zoom'])}:{int(gh*c['zoom'])},crop={gw}:{gh}" if c.get("zoom", 1) > 1 else "") + f"{zoom},format=yuva420p[g0];[g0][5:v]alphamerge[g];"
         f"[0:v]format=yuva420p,trim=duration={dur}[bg];[bg][g]overlay={gx}:{gy}[v1];")
    if cam:
        x, y, w, h = cam; cx, cy, cw, ch = L["cam"]
        g += (f"[cs]crop={w}:{h}:{x}:{y},scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch},format=yuva420p[c0];"
              f"[c0][6:v]alphamerge[cm];[v1][cm]overlay={cx}:{cy}[v2];")
    else: g += "[cs]nullsink;[v1]null[v2];"
    g += (f"[v2][2:v]overlay=0:0[v3];[v3][3:v]overlay=0:0[v4];[v4][4:v]overlay=0:0,ass={out/'subs.ass'},format=yuv420p[v];"
          f"[7:a]volume={C['sfx']['whoosh_db']}dB[w];[8:a]volume={C['sfx']['impact_db']}dB,adelay={int(P*1000)}|{int(P*1000)}[im];"
          f"[1:a]aresample=48000[src];[src][w][im]amix=inputs=3:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    subprocess.run(["ffmpeg","-y","-v","error",*inp,"-filter_complex",g,"-map","[v]","-map","[a]","-t",str(dur),
        "-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-b:a","160k","-movflags","+faststart",str(out/"video.mp4")], check=True)
    subprocess.run(["ffmpeg","-y","-v","error","-ss",str(P),"-i",str(out/"video.mp4"),"-frames:v","1","-vf","scale=360:-2",str(out/"thumb.jpg")])
    tags = " ".join(dict.fromkeys(cp.get("hashtags", []) + CH["hashtags_base"]))
    desc = f"{cp['description']}\n\nCréditos: {c['streamer']}\nSegue o {CH['handle']} 🔔\n\n{tags}"
    (out/"descricao.txt").write_text(f"TÍTULO: {cp['title']}\n\nDESCRIÇÃO:\n{desc}\n")
    (out/"meta.json").write_text(json.dumps({"title": cp["title"], "description": desc, "streamer": c["streamer"],
        "status": "aguardando_aprovacao"}, ensure_ascii=False, indent=1))
    return out

def compile_(clips, comp, out_root):
    """Compilação: renderiza cada trecho com o mesmo título de tela e concatena (>60 s p/ monetização)."""
    tmp = out_root/"_parts"; parts = []
    for k, cid in enumerate(comp["order"]):
        c = next(x for x in clips if x["id"] == cid); cp = {**comp, **COPY.get(cid, {})}
        parts.append(render(c, cp, tmp, k+1)/"video.mp4")
    out = out_root/f"01_{slug(comp['title'])}"; out.mkdir(parents=True, exist_ok=True)
    (tmp/"list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",str(tmp/"list.txt"),"-c:v","libx264","-preset","veryfast","-crf","20",
        "-c:a","aac","-b:a","160k","-af","loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000","-movflags","+faststart",str(out/"video.mp4")], check=True)
    credits = ", ".join(dict.fromkeys(next(x for x in clips if x["id"] == cid)["streamer"] for cid in comp["order"]))
    for f in ("descricao.txt", "meta.json"):
        t = (parts[0].parent/f).read_text(); first = next(x for x in clips if x["id"] == comp["order"][0])["streamer"]
        (out/f).write_text(t.replace(f"Créditos: {first}", f"Créditos: {credits}").replace(json.dumps(first, ensure_ascii=False)[1:-1], credits, 1) if f == "meta.json" else t.replace(f"Créditos: {first}", f"Créditos: {credits}"))
    subprocess.run(["ffmpeg","-y","-v","error","-ss","3","-i",str(out/"video.mp4"),"-frames:v","1","-vf","scale=360:-2",str(out/"thumb.jpg")])
    import shutil; shutil.rmtree(tmp); return out

if __name__ == "__main__":
    b = pathlib.Path(sys.argv[1]); clips = json.loads((b/"pending.json").read_text())
    copy = json.loads((b/"copy.json").read_text()) if (b/"copy.json").exists() else {}
    COPY = copy; out_root = R/"output"/b.name
    if "_compilation" in copy: print("[ok]", compile_(clips, copy["_compilation"], out_root)); sys.exit()
    for n, c in enumerate(clips, 1):
        cp = copy.get(c["id"])
        if not cp:
            if c["lang"] != "pt": print("[aguardando tradução]", c["id"]); continue
            cp = {"title": random.choice(["ELE NÃO ESPERAVA ISSO NO GTA 😱", "O SUSTO QUE ELE LEVOU KKKK", "A REAÇÃO DELE FOI ABSURDA"]),
                  "description": "Olha a reação dele 😂", "hashtags": ["#gtarp", "#lives"]}
        print("[ok]", render(c, cp, out_root, n))
