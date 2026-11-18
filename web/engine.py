"""Adaptador entre o webapp e o motor do João (live/detect.py, live/render_live.py, capture/stack.py).
O motor NÃO é reescrito: este módulo só chama as funções existentes com parâmetros por cliente.
Mudanças de comportamento feitas aqui (e por quê):
  1. Limiar adaptativo de picos: o limiar fixo de 14 dB devolveu 0 cortes num VOD real de 4 min (auditoria);
     tentamos 14 → 10 → 8 → 6 dB usando a mesma função detect.peaks.
  2. Idioma detectado: detect.transcribe descarta o idioma; aqui reaproveitamos o mesmo modelo em cache
     para obter info.language quando o cliente escolhe "automático".
  3. Pacote de assets por cliente: logo/mascote do ClipeiAki são da marca do canal; para clientes o renderer
     recebe um diretório de assets com a moldura neutra + @handle do cliente (render_live.A/L/C por chamada).
  4. Recursos premium (Creator Studio): SFX e punch-in zoom já existentes no render; desligados no Creator."""
import copy as _copy, json, pathlib, subprocess, sys, threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "live")); sys.path.insert(0, str(ROOT / "capture"))
import detect, render_live as rl  # noqa: E402  (motor do João)

TPL = ROOT / "template/assets"
FONT = next((p for p in ["/usr/share/fonts/opentype/inter/Inter-Bold.otf", "/usr/share/fonts/truetype/inter/Inter-Bold.ttf"]
             if pathlib.Path(p).exists()), None)
_render_lock = threading.Lock()
_BASE_C, _BASE_L = _copy.deepcopy(rl.C), _copy.deepcopy(rl.L)


class EngineError(Exception):
    """Erro com mensagem segura para mostrar ao cliente."""


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                        "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
    if r.returncode: raise EngineError("Arquivo não reconhecido como vídeo.")
    j = json.loads(r.stdout or "{}"); st = j.get("streams", [])
    v = next((s for s in st if s.get("codec_type") == "video"), None)
    a = next((s for s in st if s.get("codec_type") == "audio"), None)
    dur = float(j.get("format", {}).get("duration") or 0)
    if not v or dur <= 0: raise EngineError("Arquivo sem trilha de vídeo válida.")
    if not a: raise EngineError("O vídeo precisa ter áudio: a detecção de momentos usa o áudio.")
    return {"duration": dur, "width": v.get("width"), "height": v.get("height")}


def _transcribe(path, s, e, lang):
    """Mesmo modelo/parâmetros de detect.transcribe, devolvendo também o idioma detectado."""
    from faster_whisper import WhisperModel
    m = detect.transcribe.m = getattr(detect.transcribe, "m", None) or WhisperModel("small", compute_type="int8")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(s), "-t", str(e - s), "-i", str(path), "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    segs, info = m.transcribe(np.frombuffer(raw, np.float32), language=lang, word_timestamps=True, vad_filter=True)
    words = [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for g in segs for w in (g.words or [])]
    return words, info.language


def find_moments(src, max_clips):
    d = dict(_BASE_C["detect"]); d["max_clips_per_cycle"] = max_clips
    db = detect.loudness(src, d["window_s"]); dur = len(db) * d["window_s"]
    if len(db) == 0: raise EngineError("Não foi possível ler o áudio do vídeo.")
    if dur <= 59:  # vídeo curto: o vídeo inteiro é o corte (regra do João)
        return dur, [(0.0, dur, float(np.argmax(db)) * d["window_s"], float(db.max() - np.median(db)))]
    for thr in dict.fromkeys([d["peak_db_above_median"], 10, 8, 6]):
        pk = detect.peaks(db, {**d, "peak_db_above_median": thr})
        if pk: break
    if not pk:  # áudio sem picos (ex.: fala constante): pega o trecho mais alto
        pk = [(int(np.argmax(db)), float(db.max() - np.median(db)))]
    out = []
    for i, strength in pk:
        p = i * d["window_s"]; s = max(0, p - d["pre_s"]); e = min(dur, p + d["post_s"])
        out.append((s, e, p - s, strength))
    return dur, out


def webcam_layout(src):
    try:
        import stack  # capture/stack.py (YuNet)
        return stack.layout(src)
    except Exception:
        return {"webcam": None}


def analyze(src, lang, max_clips, progress=lambda p, s: None):
    """Detecta momentos + transcreve só os trechos. Retorna (clips, idioma)."""
    progress(5, "Lendo o áudio")
    dur, moments = find_moments(src, max_clips)
    progress(20, "Detectando webcam e enquadramento")
    lay = webcam_layout(src)
    clips, det_lang = [], None if lang == "auto" else lang
    for k, (s, e, peak, strength) in enumerate(moments):
        progress(25 + 60 * k / max(1, len(moments)), f"Transcrevendo momento {k + 1} de {len(moments)}")
        words, got = _transcribe(src, s, e, det_lang)
        det_lang = det_lang or got
        clips.append({"id": f"m{k}", "src": str(src), "lang": det_lang, "kind": "upload", "start": round(s, 2),
                      "end": round(e, 2), "peak": round(peak, 2), "strength": round(strength, 1), "words": words,
                      "webcam": lay.get("webcam"), **({"focus": lay["focus"]} if lay.get("focus") is not None else {})})
    for c in clips: c["lang"] = det_lang or "en"
    return clips, det_lang or "en"


def brand_pack(dest, handle):
    """Diretório de assets do cliente: moldura/fundo/máscaras do template + rodapé com o @handle (sem marca ClipeiAki)."""
    dest.mkdir(parents=True, exist_ok=True)
    for f in ("background.png", "frame_full.png", "frame_webcam.png", "mask_cam.png", "mask_game_cam.png", "mask_game_full.png"):
        t = dest / f
        if not t.exists(): t.symlink_to(TPL / f)
    Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(dest / "mascot.png")
    logo = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    if handle and FONT:
        txt = handle if handle.startswith("@") else "@" + handle
        dr = ImageDraw.Draw(logo); size = 64
        while size > 30:
            fnt = ImageFont.truetype(FONT, size); w = dr.textlength(txt, font=fnt)
            if w <= 900: break
            size -= 4
        dr.text((540, 1822), txt, font=fnt, fill=(255, 255, 255, 255), anchor="mm")
    logo.save(dest / "logo.png")
    return dest


def render(clip, cp, out_root, n, assets_dir, premium):
    """Chama render_live.render (motor do João) com assets e recursos do plano do cliente."""
    C = _copy.deepcopy(_BASE_C); L = _copy.deepcopy(_BASE_L)
    L["caption_xy"] = [540, L["caption_xy"][1]]  # sem mascote: legenda centralizada
    if not premium:
        # zoom desligado sem tirar o zoompan do grafo: com broll.enabled=false + webcam o render do João quebra
        # (crop ímpar 1014x801 vira 800 e o alphamerge falha — bug latente encontrado na auditoria).
        C["broll"]["enabled"] = True; C["broll"]["seconds"] = -1.0  # janela vazia: between(it,P-0.2,P-1) nunca é verdadeiro
        C["sfx"]["whoosh_db"] = -90; C["sfx"]["impact_db"] = -90
    with _render_lock:
        old = rl.A, rl.C, rl.L
        rl.A, rl.C, rl.L = pathlib.Path(assets_dir), C, L
        try:
            return rl.render(clip, cp, pathlib.Path(out_root), n)
        except subprocess.CalledProcessError as e:
            raise EngineError("Falha ao renderizar o corte (ffmpeg).") from e
        finally:
            rl.A, rl.C, rl.L = old
