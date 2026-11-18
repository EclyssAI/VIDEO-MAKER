"""Varre clips da Twitch (últimos 7 dias) de vários streamers e guarda só os de GTA. Uso: python capture/harvest.py"""
import subprocess, json, pathlib, concurrent.futures as cf
R = pathlib.Path(__file__).resolve().parent.parent; OUT = R/"work/stack/clips.jsonl"
STREAMERS = """xqc kaicenat summit1g jynxzi caseoh_ ramee lord_kebun fanfan ssaab penta hasanabi tarik buddha sykkuno anthonyz
mrbossftw 4head ray__c dasmehdi koil moonmoon pokelawls nmplol shroud timthetatman lirik cohhcarnage plaqueboymax stableronaldo
fanum duke_dennis agent00 zackrawrr erobb221 jakenbakelive kyle sodapoppin esfandtv mizkif maximum""".split()

def listing(ch):
    r = subprocess.run(["yt-dlp", "--flat-playlist", "--playlist-end", "30", "--print", "%(url)s",
                        f"https://www.twitch.tv/{ch}/clips?filter=clips&range=7d"], capture_output=True, text=True, timeout=90)
    return [u for u in r.stdout.split() if "/clip/" in u]

def meta(u):
    r = subprocess.run(["yt-dlp", "--skip-download", "-J", u], capture_output=True, text=True, timeout=60)
    if r.returncode: return None
    d = json.loads(r.stdout); cat = (d.get("categories") or [""])[0]
    if "Grand Theft Auto" not in cat: return None
    return {"url": u, "views": d.get("view_count", 0), "dur": d.get("duration"), "game": cat, "streamer": d.get("channel") or u.split("/")[3],
            "login": u.split("/")[3], "title": d.get("title"), "date": d.get("upload_date")}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1: STREAMERS = sys.argv[1:]; OUT = S2 = R/"work/stack/clips_extra.jsonl"
    with cf.ThreadPoolExecutor(12) as ex: urls = [u for l in ex.map(listing, STREAMERS) for u in l]
    print("clips listados:", len(urls), flush=True)
    with cf.ThreadPoolExecutor(16) as ex: rows = [m for m in ex.map(meta, urls) if m]
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    print("clips de GTA:", len(rows), "duração total:", sum(r["dur"] or 0 for r in rows), "s")
