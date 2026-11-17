"""Clone ViceScrap + ViceRepost: varre perfis públicos, ranqueia por outlier de views, baixa os virais novos.
Uso: python capture/scrap.py  -> work/batch/<data>_scrap/*.mp4 + sources.json"""
import json, subprocess, statistics, datetime, pathlib, yaml
R = pathlib.Path(__file__).resolve().parent.parent; C = yaml.safe_load((R/"config/sources.yaml").read_text())
SEEN = R/"logs/seen.json"; COOK = R/"config/secrets/cookies.txt"
ck = ["--cookies", str(COOK)] if COOK.exists() else []

def listing(url):
    r = subprocess.run(["yt-dlp", "--flat-playlist", "-J", "--playlist-end", str(C["scan_last"]), *ck, url], capture_output=True, text=True)
    if r.returncode: print("[falhou]", url, r.stderr.strip()[-200:]); return []
    return [e for e in json.loads(r.stdout).get("entries", []) if e.get("view_count")]

def run():
    seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set(); cands = []
    for p in C["profiles"]:
        es = listing(p["url"])
        if not es: continue
        med = statistics.median(e["view_count"] for e in es) or 1
        for e in es:
            url = e.get("url") or e.get("webpage_url"); o = e["view_count"]/med
            if url not in seen and o >= C["min_outlier"]:
                cands.append({**p, "src_url": url, "views": e["view_count"], "outlier": round(o, 1), "credit": e.get("uploader") or p["url"]})
    cands = sorted(cands, key=lambda c: -c["outlier"])[:C["top_per_run"]]
    b = R/"work/batch"/(datetime.datetime.now().strftime("%Y%m%d_%H%M") + "_scrap"); b.mkdir(parents=True, exist_ok=True); meta = {}
    for i, c in enumerate(cands):
        name = f"scrap{i:02d}"
        if subprocess.run(["yt-dlp", "-q", "-f", "mp4/best", *ck, "-o", str(b/f"{name}.mp4"), c["src_url"]]).returncode == 0:
            meta[name] = {"lang": c["lang"], "kind": c["kind"], "credit": c["credit"], "webcam": None, "views": c["views"], "outlier": c["outlier"], "source": c["src_url"]}
            seen.add(c["src_url"])
    (b/"sources.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1)); SEEN.write_text(json.dumps(sorted(seen)))
    print(f"[scrap] {len(meta)} virais baixados -> {b}"); return b

if __name__ == "__main__": run()
