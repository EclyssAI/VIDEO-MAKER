"""prepare: lê input/queue.txt (1 link ou caminho por linha; opcional '| credito | tipo'),
baixa, transcreve (faster-whisper local) e grava work/<id>/segments.json.
Uso: python pipeline/prepare.py [--model small]"""
import argparse, json, re, subprocess, hashlib, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent

def vid_id(s): return hashlib.md5(s.encode()).hexdigest()[:8]

def download(src, d):
    if pathlib.Path(src).exists(): return pathlib.Path(src)
    out = d / "source.mp4"
    if not out.exists():
        subprocess.run(["yt-dlp", "-f", "mp4/best", "--merge-output-format", "mp4",
                        "-o", str(out), src], check=True)
    return out

def transcribe(video, model):
    from faster_whisper import WhisperModel
    m = WhisperModel(model, compute_type="int8")
    import numpy as np
    raw = subprocess.run(["ffmpeg","-v","error","-i",str(video),"-ac","1","-ar","16000","-f","f32le","-"],capture_output=True,check=True).stdout
    segs, info = m.transcribe(np.frombuffer(raw, np.float32), word_timestamps=True, vad_filter=True)
    return info.language, [{"start": s.start, "end": s.end, "text": s.text.strip(),
            "words": [{"w": w.word.strip(), "start": w.start, "end": w.end} for w in (s.words or [])]} for s in segs]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--model", default="small"); a = ap.parse_args()
    for line in (ROOT/"input/queue.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        src, *extra = [p.strip() for p in line.split("|")]
        credit = extra[0] if extra else ""; kind = extra[1] if len(extra) > 1 else "meme"
        vid = vid_id(src); d = ROOT/"work"/vid; d.mkdir(parents=True, exist_ok=True)
        video = download(src, d)
        lang, segs = transcribe(video, a.model)
        (d/"segments.json").write_text(json.dumps(
            {"id": vid, "source": src, "video": str(video), "credit": credit, "kind": kind,
             "lang": lang, "segments": segs}, ensure_ascii=False, indent=1))
        print(f"[ok] {vid} lang={lang} segs={len(segs)} -> work/{vid}/segments.json")
