"""Stack de N vídeos (método v0.5) a partir de work/stack/clips.jsonl.
  python capture/stack.py plan 20      -> work/stack/plan.json (grupos >= ~95 s brutos por vídeo)
  python capture/stack.py prepare      -> baixa, detecta layout/rosto, transcreve, corta silêncios, cold open
                                          -> work/batch/stack_XX/pending.json + work/stack/for_claude.txt
  python capture/stack.py apply        -> lê work/stack/pt.json (traduções/títulos do Claude) -> copy.json de cada vídeo"""
import sys, json, pathlib, subprocess, collections, concurrent.futures as cf
import numpy as np
R = pathlib.Path(__file__).resolve().parent.parent; S = R/"work/stack"; sys.path.insert(0, str(R/"live"))
RAW_TARGET, MAX_CLIPS, MAX_LEN = 140, 8, 90

def plan(n):
    rows = [json.loads(l) for l in (S/"clips.jsonl").read_text().splitlines() if l.strip()]
    seen, clips = set(), []
    for r in sorted(rows, key=lambda r: -r["views"]):
        if r["url"] not in seen and (r["dur"] or 0) >= 8: seen.add(r["url"]); clips.append(r)
    by = collections.defaultdict(list)
    for c in clips: by[c["login"]].append(c)
    groups, left = [], []
    for login, cs in sorted(by.items(), key=lambda kv: -sum(c["views"] for c in kv[1])):
        cur = []
        for c in cs:
            cur.append(c)
            if sum(x["dur"] for x in cur) >= RAW_TARGET or len(cur) == MAX_CLIPS: groups.append(cur); cur = []
        left += cur
    cur = []  # sobras: compilações mistas por jogo
    for c in sorted(left, key=lambda c: (c["game"], -c["views"])):
        cur.append(c)
        if sum(x["dur"] for x in cur) >= RAW_TARGET or len(cur) == MAX_CLIPS: groups.append(cur); cur = []
    groups = sorted(groups, key=lambda g: -sum(c["views"] for c in g))[:n]
    (S/"plan.json").write_text(json.dumps(groups, ensure_ascii=False, indent=1))
    for i, g in enumerate(groups): print(f"{i:02d} {sum(c['views'] for c in g):>7} views {sum(c['dur'] for c in g):>4.0f}s {len(g)} clips {sorted({c['login'] for c in g})}")

def layout(path):
    """YuNet: rosto pequeno na mesma posição em >=40% dos frames = webcam sobreposta (layout dividido);
    rosto grande recorrente = câmera em tela cheia (focus). Rostos esporádicos (NPCs do jogo) são ignorados."""
    import cv2
    det = cv2.FaceDetectorYN.create(str(R/"template/models/yunet.onnx"), "", (960, 540), 0.85); cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1; small, big, frames = [], [], 0
    for f in np.linspace(0.08, 0.92, 9):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n*f)); ok, im = cap.read()
        if not ok: continue
        frames += 1; _, d = det.detect(cv2.resize(im, (960, 540)))
        for x, y, w, h in ((d[:, :4]*2).tolist() if d is not None else []):
            (big if h >= 230 else small).append((x, y, w, h))
    if not frames: return {"webcam": None}
    if len(big) >= 0.4*frames:
        x, y, w, h = np.median(big, 0); return {"webcam": None, "focus": round(float((x+w/2)/1920), 3)}
    best = None
    for c in small:  # maior grupo de rostos pequenos na mesma posição
        grp = [o for o in small if abs(o[0]-c[0]) < 150 and abs(o[1]-c[1]) < 150]
        if best is None or len(grp) > len(best): best = grp
    if best and len(best) >= 0.4*frames:
        x, y, w, h = np.median(best, 0); cx, cy = x+w/2, y+h*0.8; W = min(1920, max(360, w*5)); H = W/2.43
        X = int(max(0, min(1920-W, cx-W/2))); Y = int(max(0, min(1080-H, cy-H/2)))
        return {"webcam": [X, Y, int(W), int(H)]}
    return {"webcam": None}

def runs(words, db, win=0.5, gap=0.7, dur=0):
    """Trechos com fala (palavras com gap < 0.7 s) + gritos sem fala (loudness alta). Corta o resto."""
    keep = [[max(0, w["s"]-0.15), w["e"]+0.25] for w in words]
    med = np.median(db) if len(db) else 0
    keep += [[i*win, i*win+win] for i, v in enumerate(db) if v > med + 10]
    keep.sort(); out = []
    for s, e in keep:
        if out and s - out[-1][1] < gap: out[-1][1] = max(out[-1][1], e)
        else: out.append([s, e])
    out = [[s, min(e, dur)] for s, e in out if e - s >= 1.2]
    split = []
    for s, e in out:  # trecho > 10 s vira 2+ (ritmo visual)
        while e - s > 10: split.append([s, s+7]); s += 7
        split.append([s, e])
    return split

def prep_clip(job):
    import detect
    i, k, c, B = job; f = B/f"c{k}.mp4"; dl = S/"dl"/(c["url"].rstrip("/").split("/")[-1] + ".mp4"); dl.parent.mkdir(exist_ok=True)
    if not dl.exists(): subprocess.run(["yt-dlp", "-q", "-o", str(dl), c["url"]], timeout=180)
    if dl.exists() and not f.exists(): f.symlink_to(dl)
    if not f.exists(): return None
    db = detect.loudness(f, 0.5); dur = len(db)*0.5
    return {"k": k, "file": f, "clip": c, "layout": layout(f), "db": db, "dur": dur}

def prepare():
    import detect
    plan_ = json.loads((S/"plan.json").read_text()); jobs = []
    only = {int(x) for x in __import__("os").environ.get("ONLY", "").split(",") if x}
    for i, g in enumerate(plan_):
        if only and i not in only: continue
        B = R/"work/batch"/f"stack_{i:02d}"; B.mkdir(parents=True, exist_ok=True)
        jobs += [(i, k, c, B) for k, c in enumerate(g)]
    with cf.ThreadPoolExecutor(8) as ex: res = [r for r in ex.map(prep_clip, jobs)]
    lines = []
    for i, g in enumerate(plan_):
        if only and i not in only: continue
        B = R/"work/batch"/f"stack_{i:02d}"; items = [r for r, j in zip(res, jobs) if j[0] == i and r]
        entries, best = [], None
        for it in items:
            words = detect.transcribe(it["file"], 0, it["dur"], "en")
            for s, e in runs(words, it["db"], dur=it["dur"]):
                eid = f"c{it['k']}_{int(s*10)}"; ws = [w for w in words if w["s"] >= s-0.05 and w["e"] <= e+0.3]
                seg = it["db"][int(s/0.5):int(e/0.5)+1]; pk = (int(np.argmax(seg))*0.5) if len(seg) else 0
                ent = {"id": eid, "streamer": f"{it['clip']['streamer']} (twitch.tv/{it['clip']['login']})", "src": str(it["file"]), "lang": "en",
                       "kind": "stack", "start": round(s, 2), "end": round(e, 2), "peak": pk, "strength": 0, "words": [], **it["layout"],
                       "blocks": [{"s": round(b[0]["s"]-s, 2), "e": round(b[-1]["e"]-s, 2), "en": " ".join(w["w"] for w in b)}
                                  for b in (ws[j:j+3] for j in range(0, len(ws), 3))]}
                ent["webcam"] = ent.get("webcam"); entries.append(ent)
                lvl = float(seg.max()) if len(seg) else -99
                if best is None or lvl > best[0]: best = (lvl, ent, s+pk)
        seen_txt = []  # remove trechos com fala repetida (clips diferentes do mesmo momento)
        def _w(e): return set(" ".join(b["en"] for b in e["blocks"]).lower().replace(",", "").replace(".", "").split())
        keep = []
        for e in entries:
            w = _w(e)
            if len(w) >= 4 and any(len(w & o) / len(w) >= 0.6 for o in seen_txt): continue
            seen_txt.append(w); keep.append(e)
        entries = keep
        if best and best[1] not in entries: best = max(((float(it["db"].max()), e, e["start"]+e["peak"]) for e in entries for it in items if str(it["file"]) == e["src"]), default=None, key=lambda t: t[0])
        if best:  # cold open: 2 s em volta do pico mais alto do vídeo
            _, ent, p = best; s = max(0, p-1.2); e = s+2.2
            t0 = {**ent, "id": "t0", "start": round(s, 2), "end": round(e, 2), "peak": round(p-s, 2), "zoom": 1.15,
                  "blocks": [b | {"s": round(b["s"]+ent["start"]-s, 2), "e": round(b["e"]+ent["start"]-s, 2)} for b in ent["blocks"]
                             if b["e"]+ent["start"] > s and b["s"]+ent["start"] < e]}
            entries.insert(0, t0)
        while len(entries) > 2 and sum(x["end"]-x["start"] for x in entries) - (entries[-1]["end"]-entries[-1]["start"]) >= 61 \
                and sum(x["end"]-x["start"] for x in entries) > MAX_LEN: entries.pop()   # teto de 90 s
        z = 1.0
        for ent in entries[1:]: z = 1.12 if z == 1.0 else 1.0; ent.setdefault("zoom", z)
        (B/"pending.json").write_text(json.dumps(entries, ensure_ascii=False, indent=1))
        total = sum(x["end"]-x["start"] for x in entries)
        lines.append(f"## {i:02d} {total:.0f}s streamers={sorted({x['streamer'].split(' (')[0] for x in entries})} jogo={g[0]['game']} titulos_twitch={[c['title'] for c in g]}")
        lines += [f"{ent['id']}#{n}|{b['en']}" for ent in entries for n, b in enumerate(ent["blocks"])]
    (S/(f"for_claude_{'_'.join(map(str, sorted(only)))}.txt" if only else "for_claude.txt")).write_text("\n".join(lines)); print("ok ->", S/"for_claude.txt")

def parse_pt():
    """pt.txt: '## NN|tela|título|descrição (' / ' = quebra)|#tags' + 'DROP id id' + 'id#n|TRADUÇÃO' ('!' = destaque)."""
    out, cur = {}, None
    for line in (S/"pt.txt").read_text().splitlines():
        if line.startswith("## "):
            n, scr, tit, desc, tags = line[3:].split("|"); cur = out[n] = {"screen_title": scr, "title": tit,
                "description": desc.replace(" / ", "\n"), "hashtags": tags.split(), "blocks": {}, "drop": []}
        elif line.startswith("DROP "): cur["drop"] += line.split()[1:]
        elif "|" in line: k, v = line.split("|", 1); cur["blocks"][k] = v
    return out

def apply():
    pt = parse_pt()
    for i, meta in pt.items():
        B = R/"work/batch"/f"stack_{int(i):02d}"; P = json.loads((B/"pending.json").read_text())
        drop = set(meta.get("drop", []))
        if drop:
            bad = [e for e in P if e["id"] in drop]
            P = [e for e in P if e["id"] not in drop and not (e["id"] == "t0" and any(b["src"] == e["src"] and b["start"] < e["end"] and e["start"] < b["end"] for b in bad))]
            (B/"pending.json").write_text(json.dumps(P, ensure_ascii=False, indent=1))
        tr = meta.get("blocks", {}); copy = {"_compilation": {"order": [e["id"] for e in P], **{k: meta[k] for k in ("screen_title", "title", "description", "hashtags")}}}
        for e in P:
            caps = []
            for n, b in enumerate(e.get("blocks", [])):
                t = tr.get(f"{e['id']}#{n}")
                if t: caps.append({"s": max(0, b["s"]), "e": min(e["end"]-e["start"], b["e"]+0.15), "t": t.lstrip("!"), "hl": t.startswith("!")})
            for a, b in zip(caps, caps[1:]): a["e"] = min(a["e"], b["s"])   # nunca duas legendas ao mesmo tempo
            copy[e["id"]] = {"captions": caps}
        (B/"copy.json").write_text(json.dumps(copy, ensure_ascii=False, indent=1))
        print(i, f"{sum(e['end']-e['start'] for e in P):.0f}s", len(P), "trechos", sum(len(copy[e['id']]['captions']) for e in P), "legendas")
    print("copy.json gerados:", len(pt))

if __name__ == "__main__":
    a = sys.argv[1:]
    {"plan": lambda: plan(int(a[1]) if len(a) > 1 else 20), "prepare": prepare, "apply": apply}[a[0]]()
