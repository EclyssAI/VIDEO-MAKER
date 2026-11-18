"""Títulos, descrição e legendas PT-BR dos cortes.
Na versão do João isso era feito manualmente por uma sessão do Claude Code lendo for_claude.txt + skill /viralizei.
No SaaS: chamada à Claude API (SDK oficial) quando ANTHROPIC_API_KEY está configurada; sem chave, cai num
modo determinístico (título padrão editável + legenda na língua original) — o fluxo continua funcionando."""
import json, os, logging

log = logging.getLogger("copywriter")
MODEL = os.environ.get("VM_CLAUDE_MODEL", "claude-opus-5-5")
FALLBACK_TITLES = ["O MOMENTO QUE NINGUÉM ESPERAVA", "OLHA O QUE ACONTECEU AQUI", "ESSA REAÇÃO FOI ABSURDA",
                   "VOCÊ NÃO VAI ACREDITAR NISSO", "O FINAL DESSE CLIPE"]

SYSTEM = """Você escreve a embalagem de cortes verticais (TikTok, Reels, Shorts) para criadores brasileiros.
Regras (método /viralizei do VIDEO-MAKER):
- screen_title: texto na tela, MAIÚSCULAS, até 32 caracteres, curiosidade/choque, sem emoji, sem hashtag.
- title: título do post, até 60 caracteres, termina com pergunta ou gatilho de curiosidade; pode ter 1 emoji.
- description: 1ª linha é gancho; 2-3 linhas no total; sem hashtags.
- hashtags: 4 a 6, em minúsculas, começando com #.
- captions: traduza CADA bloco para português do Brasil natural e falado (gírias quando couber), mesmo índice;
  só a tradução da fala, sem comentários; até 6 palavras por bloco; marque hl=true no bloco mais impactante.
  Se a fala já estiver em português, apenas corrija a transcrição. Blocos sem fala útil: texto vazio."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["clips"], "properties": {"clips": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "screen_title", "title", "description", "hashtags", "captions"],
        "properties": {"id": {"type": "string"}, "screen_title": {"type": "string"}, "title": {"type": "string"},
            "description": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}},
            "captions": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["i", "t", "hl"], "properties": {"i": {"type": "integer"}, "t": {"type": "string"},
                                                             "hl": {"type": "boolean"}}}}}}}}}


def blocks(words, per=3):
    return [{"i": n, "s": g[0]["s"], "e": max(g[-1]["e"], g[0]["s"] + 0.4), "t": " ".join(w["w"] for w in g)}
            for n, g in enumerate(words[i:i + per] for i in range(0, len(words), per))]


def enabled(): return bool(os.environ.get("ANTHROPIC_API_KEY"))


def fallback(clip, k=0):
    caps = [{"s": b["s"], "e": b["e"], "t": b["t"]} for b in blocks(clip["words"])]
    t = FALLBACK_TITLES[k % len(FALLBACK_TITLES)]
    return {"screen_title": t, "title": t.capitalize() + "?", "description": "Olha esse momento até o final.",
            "hashtags": ["#cortes", "#clips", "#viral", "#fyp"], "captions": caps, "source": "padrao"}


def _call(clips, lang, context):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                                 base_url=os.environ.get("VM_ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                                 timeout=180, max_retries=2)
    lines = [f"Contexto do projeto: {context}", f"Idioma da fala: {lang}", ""]
    for c in clips:
        lines.append(f"## clip {c['id']} ({c['end'] - c['start']:.0f}s)")
        lines += [f"{b['i']}|{b['t']}" for b in blocks(c["words"])]
    r = client.messages.create(model=MODEL, max_tokens=16000, system=SYSTEM, output_config={
        "effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": "\n".join(lines)}])
    if r.stop_reason == "refusal": raise RuntimeError("refusal")
    return json.loads(next(b.text for b in r.content if b.type == "text"))["clips"]


def make_copy(clips, lang, context=""):
    """Devolve {clip_id: copy}. Nunca levanta exceção: falha da API -> modo padrão (registrado no log)."""
    out = {c["id"]: fallback(c, k) for k, c in enumerate(clips)}
    if not enabled() or not clips: return out
    try:
        for item in _call(clips, lang, context[:200]):
            c = next((x for x in clips if x["id"] == item["id"]), None)
            if not c: continue
            bl = {b["i"]: b for b in blocks(c["words"])}
            caps = [{"s": bl[x["i"]]["s"], "e": bl[x["i"]]["e"], "t": x["t"].strip(), "hl": bool(x["hl"])}
                    for x in item["captions"] if x["i"] in bl and x["t"].strip()]
            out[c["id"]] = {"screen_title": item["screen_title"][:40], "title": item["title"][:100],
                            "description": item["description"][:2000], "hashtags": item["hashtags"][:8],
                            "captions": caps, "source": "claude"}
    except Exception as e:  # rede, chave inválida, recusa, JSON — o cliente ainda recebe os cortes
        log.warning("claude copy falhou: %s", str(e)[:300])
    return out
