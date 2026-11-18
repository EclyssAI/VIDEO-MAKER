"""Análise de momentos de live pela Claude API (SDK oficial).
Enviamos SÓ o que está registrado: N frames JPEG (com o timestamp da transmissão de cada um), a transcrição da janela,
um trecho do contexto anterior e os sinais medidos (áudio/imagem/palavras). A resposta é JSON com schema estruturado e
ainda é validada aqui (timestamps dentro da janela, duração do corte). Nada além disso é "visto" pelo modelo."""
import base64, hashlib, json, os, re, time

MODEL = os.environ.get("LIVE_CLAUDE_MODEL", os.environ.get("VM_CLAUDE_MODEL", "claude-opus-5-5"))
# USD por milhão de tokens (entrada, saída) — usados para o orçamento da sessão. Ajustável por env.
MAX_TOKENS = int(os.environ.get("LIVE_CLAUDE_MAX_TOKENS", "3000"))  # inclui o raciocínio do modelo
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}

SYSTEM = """Você é o editor do ClipeiAki e analisa trechos de uma transmissão ao vivo da Twitch para decidir se viram
um corte vertical (TikTok/Reels/Shorts). Você recebe apenas alguns frames com o horário da transmissão de cada um, a
transcrição com timestamps e os sinais medidos (picos de áudio, mudanças de imagem, palavras). Não invente o que não está
nos dados: descreva só o que os frames e a transcrição mostram. Use sempre os timestamps da transmissão (t, em segundos)
recebidos. Decida "clip" só se houver um momento forte (reação, susto, piada, jogada, briga, revelação) que funcione
sozinho em 8 a 45 segundos; caso contrário "skip". start_t/end_t precisam ficar dentro da janela informada e começar
um pouco antes do gatilho. screen_title: até 32 caracteres, MAIÚSCULAS, português do Brasil, sem emoji.
title: até 60 caracteres. reason: justificativa objetiva citando timestamps. summary: 1-2 frases do que acontece."""

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["decision", "confidence", "start_t", "end_t", "screen_title", "title", "reason", "summary", "events"],
          "properties": {
              "decision": {"type": "string", "enum": ["clip", "skip"]},
              "confidence": {"type": "number"},
              "start_t": {"type": "number"}, "end_t": {"type": "number"},
              "screen_title": {"type": "string"}, "title": {"type": "string"},
              "reason": {"type": "string"}, "summary": {"type": "string"},
              "events": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                     "required": ["t", "description"],
                                                     "properties": {"t": {"type": "number"}, "description": {"type": "string"}}}}}}


class ClaudeUnavailable(Exception): pass
class InvalidDecision(Exception):
    def __init__(self, msg, meta=None):
        super().__init__(msg); self.meta = meta  # meta presente = a chamada foi feita e deve ser cobrada


def status():
    """Estado de configuração real (sem chamar a API)."""
    if os.environ.get("LIVE_CLAUDE_ENABLED", "1") != "1": return "disabled", "Análise Claude desligada pela configuração do servidor."
    if not os.environ.get("ANTHROPIC_API_KEY"): return "disabled", "ANTHROPIC_API_KEY não configurada no servidor."
    return "ready", f"Modelo {MODEL}"


def cost(usage, model=None):
    pin, pout = PRICES.get(model or MODEL, PRICES.get(MODEL, PRICES["claude-opus-5-5"]))
    tin = (usage.get("input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0) * 1.25 + (usage.get("cache_read_input_tokens") or 0) * 0.1
    return round(tin * pin / 1e6 + (usage.get("output_tokens") or 0) * pout / 1e6, 6)


def estimate(n_frames, text_chars):
    """Estimativa conservadora antes da chamada (para não estourar o orçamento)."""
    pin, pout = PRICES.get(MODEL, PRICES["claude-opus-5-5"])
    tin = 1200 + n_frames * 450 + text_chars / 3
    return round(tin * pin / 1e6 + MAX_TOKENS * pout / 1e6, 6)  # pior caso: resposta usa todo o max_tokens


def build_content(frames, window, transcript, context, signals):
    """frames: [(t_stream, wall, jpeg_bytes)]. Retorna (content, [sha256])."""
    content, shas = [], []
    for k, (t, wall, data) in enumerate(frames):
        shas.append(hashlib.sha256(data).hexdigest())
        content.append({"type": "text", "text": f"Frame {k + 1}: t={t:.1f}s da transmissão ({time.strftime('%H:%M:%S', time.gmtime(wall))} UTC)"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": "\n".join([
        f"Janela candidata: t={window[0]:.1f}s até t={window[1]:.1f}s.",
        f"Sinais medidos: {json.dumps(signals, ensure_ascii=False)}",
        "Contexto anterior (transcrição):", context or "(sem fala)",
        "Transcrição da janela:", transcript or "(sem fala detectada)",
        "Responda com o JSON pedido."])})
    return content, shas


def validate(d, window):
    w0, w1 = window
    if d["decision"] not in ("clip", "skip"): raise InvalidDecision("decision inválida")
    d["confidence"] = max(0.0, min(1.0, float(d["confidence"])))
    for e in d["events"]:
        if not (w0 - 1 <= e["t"] <= w1 + 1): raise InvalidDecision(f"evento fora da janela: t={e['t']}")
    if d["decision"] == "clip":
        s, e = float(d["start_t"]), float(d["end_t"])
        s, e = max(w0, s), min(w1, e)
        if e - s < 5 or e - s > 60: raise InvalidDecision(f"duração do corte inválida: {s:.1f}–{e:.1f}")
        d["start_t"], d["end_t"] = round(s, 2), round(e, 2)
        d["screen_title"] = re.sub(r"[\r\n\t\\{}]+", " ", d["screen_title"]).strip()[:40] or "MOMENTO DA LIVE"
        d["title"] = re.sub(r"[\r\n\t]+", " ", d["title"]).strip()[:100]
    return d


def analyze(frames, window, transcript, context, signals):
    """Chama a API. Retorna dict com decisão validada + métricas. Levanta ClaudeUnavailable/InvalidDecision."""
    st, detail = status()
    if st != "ready": raise ClaudeUnavailable(detail)
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                                 base_url=os.environ.get("VM_ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                                 timeout=float(os.environ.get("LIVE_CLAUDE_TIMEOUT", "90")), max_retries=1)
    content, shas = build_content(frames, window, transcript, context, signals)
    req = dict(model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM, messages=[{"role": "user", "content": content}],
               output_config={"effort": os.environ.get("LIVE_CLAUDE_EFFORT", "low"), "format": {"type": "json_schema", "schema": SCHEMA}})
    t0 = time.time()
    def send():
        try:  # fallback de recusa no servidor (recomendado para este modelo); se a API recusar o parâmetro, repete sem ele
            return client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **req)
        except anthropic.BadRequestError as e:
            if "fallback" not in str(e).lower(): raise ClaudeUnavailable(f"Requisição recusada: {str(e)[:200]}")
        return client.messages.create(**req)
    try:
        r = send()
    except anthropic.AuthenticationError:
        raise ClaudeUnavailable("Chave da API inválida.")
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        raise ClaudeUnavailable(f"Sem conexão com a API: {str(e)[:120]}")
    except anthropic.RateLimitError:
        raise ClaudeUnavailable("Limite de requisições da API atingido.")
    except anthropic.APIStatusError as e:
        raise ClaudeUnavailable(f"Erro da API ({e.status_code}).")
    except anthropic.AnthropicError as e:
        raise ClaudeUnavailable(f"Falha no SDK: {str(e)[:150]}")
    latency = round(time.time() - t0, 2)
    usage = {k: getattr(r.usage, k, 0) or 0 for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    meta = {"model": getattr(r, "model", MODEL), "latency_s": latency, "usage": usage, "cost_usd": cost(usage, getattr(r, "model", None)),
            "request_id": getattr(r, "_request_id", None), "frames_sha256": shas, "stop_reason": r.stop_reason}
    try:
        if r.stop_reason == "refusal": raise InvalidDecision("O modelo recusou a análise.")
        text = next((b.text for b in r.content if b.type == "text"), "")
        try:
            d = json.loads(text)
        except json.JSONDecodeError:
            raise InvalidDecision("Resposta sem JSON válido.")
        for k in SCHEMA["required"]:
            if k not in d: raise InvalidDecision(f"campo ausente: {k}")
        return validate(d, window), meta
    except InvalidDecision as e:
        raise InvalidDecision(str(e), meta) from None
