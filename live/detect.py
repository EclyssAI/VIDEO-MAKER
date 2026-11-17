"""Acha gritos/sustos/reações por picos de loudness e transcreve só os trechos (barato)."""
import subprocess, json, sys, pathlib, numpy as np, yaml
R = pathlib.Path(__file__).resolve().parent.parent; C = yaml.safe_load((R/"config/live.yaml").read_text())

def loudness(path, win):
    sr = 8000; raw = subprocess.run(["ffmpeg","-v","error","-i",str(path),"-ac","1","-ar",str(sr),"-f","s16le","-"],
                                    capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768; n = int(sr*win)
    a = a[:len(a)//n*n].reshape(-1, n); return 20*np.log10(np.sqrt((a**2).mean(1)) + 1e-6)

def peaks(db, d):
    thr = np.median(db) + d["peak_db_above_median"]; gap = int(d["min_gap_s"]/d["window_s"]); out = []
    for i in np.argsort(db)[::-1]:
        if db[i] < thr or len(out) >= d["max_clips_per_cycle"]: break
        if all(abs(i-j) > gap for j, _ in out): out.append((i, float(db[i]-np.median(db))))
    return sorted(out)

def transcribe(path, s, e, lang):
    from faster_whisper import WhisperModel
    m = transcribe.m = getattr(transcribe, "m", None) or WhisperModel("small", compute_type="int8")
    raw = subprocess.run(["ffmpeg","-v","error","-ss",str(s),"-t",str(e-s),"-i",str(path),"-ac","1","-ar","16000","-f","f32le","-"],
                         capture_output=True, check=True).stdout
    segs, _ = m.transcribe(np.frombuffer(raw, np.float32), language=lang, word_timestamps=True, vad_filter=True)
    return [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for g in segs for w in (g.words or [])]

def run(batch):
    d = C["detect"]; clips = []
    for st in C["streamers"]:
        src = batch/f"{st['name']}.ts"
        if not src.exists() or src.stat().st_size < 1e6: continue
        db = loudness(src, d["window_s"]); dur = len(db)*d["window_s"]
        for k, (i, strength) in enumerate(peaks(db, d)):
            p = i*d["window_s"]; s = max(0, p-d["pre_s"]); e = min(dur, p+d["post_s"])
            clips.append({"id": f"{st['name']}_{k}", "streamer": st["name"], "src": str(src), "lang": st["lang"],
                "webcam": st["webcam"], "start": s, "end": e, "peak": p-s, "strength": round(strength, 1),
                "words": transcribe(src, s, e, st["lang"])})
    (batch/"pending.json").write_text(json.dumps(clips, ensure_ascii=False, indent=1))
    # versão compacta para o Claude (economia de tokens): só texto
    (batch/"for_claude.txt").write_text("\n".join(f"{c['id']} [{c['lang']}] pico={c['peak']:.1f}s +{c['strength']}dB: " + " | ".join(f"{g[0]['s']:.1f}-{g[-1]['e']:.1f} " + " ".join(w["w"] for w in g) for g in (c["words"][i:i+3] for i in range(0, len(c["words"]), 3))) for c in clips))
    return clips

if __name__ == "__main__": print(len(run(pathlib.Path(sys.argv[1]))), "clips")
