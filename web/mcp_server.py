"""ClipeiAki Live MCP — servidor MCP oficial (SDK Python v2, MCPServer).
Controla o Live Agent e o motor existentes pelas MESMAS funções da API web (web/live/service.py): não há lógica de
captura ou edição duplicada aqui.

Autenticação: token pessoal (Conta → Tokens de API), enviado como `Authorization: Bearer cak_...` no transporte HTTP
(/mcp) ou na variável CLIPEIAKI_TOKEN no modo stdio. Cada ferramenta exige um escopo:
live:read, live:control, clips:read, clips:write. Todas as consultas são filtradas pelo dono do token.

  HTTP:  servido pelo app web em <PUBLIC_URL>/mcp
  stdio: CLIPEIAKI_TOKEN=cak_... VM_DATA_DIR=... python -m web.mcp_server"""
import asyncio, hashlib, json, logging, os, sys, threading, time
from urllib.parse import urlparse
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.types import ToolAnnotations
from mcp.server.mcpserver.utilities.types import Image
from . import db, tokens, legal, oauth
from .live import service

log = logging.getLogger("mcp")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
VERSION = "0.2.0"
_stdio = None  # (user_id, scopes) quando rodando por stdio


mcp = MCPServer(
    "ClipeiAki Live MCP", version=VERSION,
    instructions="Controla o Live Monitor do ClipeiAki (conta do dono do token): transmissões conectadas (slots do plano), "
                 "início/parada do monitoramento, estado e preview REAL (último frame gravado), momentos detectados por áudio/imagem/"
                 "palavras, evidências (frames enviados ao Claude com SHA-256, transcrição, decisão), criação e aprovação de cortes e "
                 "fila de render. O monitoramento roda no Live Agent do servidor; este chat não assiste ao vídeo continuamente. "
                 "Timestamps t_* são segundos da gravação da sessão; wall_at é horário UTC (epoch).",
    # OAuth 2.1 próprio (registro dinâmico + PKCE + consentimento) para o conector do Claude do cliente;
    # o mesmo provider também aceita os tokens pessoais cak_… (Claude Code com header Authorization).
    auth_server_provider=oauth.Provider(),
    auth=AuthSettings(issuer_url=PUBLIC_URL, resource_server_url=f"{PUBLIC_URL}/mcp", required_scopes=None,
                      service_documentation_url=f"{PUBLIC_URL}/regras-live-ia",
                      client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=oauth.SCOPES, default_scopes=oauth.SCOPES),
                      revocation_options=RevocationOptions(enabled=True), validate_token_resource=True))

RO = ToolAnnotations(read_only_hint=True)


# Limite de requisições por token (janela deslizante de 60 s, em memória do processo). Escrita/controle têm limite menor.
RATE = {"read": int(os.environ.get("MCP_RATE_READ", "120")), "write": int(os.environ.get("MCP_RATE_WRITE", "20"))}
_calls, _calls_lock = {}, threading.Lock()


def _rate(key, kind):
    now = time.time()
    with _calls_lock:
        v = [t for t in _calls.get((key, kind), []) if now - t < 60]
        if len(v) >= RATE[kind]:
            raise ToolError(f"Limite de {RATE[kind]} chamadas por minuto ({'controle/escrita' if kind == 'write' else 'leitura'}) atingido. Aguarde.")
        v.append(now); _calls[(key, kind)] = v
        if len(_calls) > 20000: _calls.clear()


def principal(scope: str) -> str:
    tok = get_access_token()
    if tok: uid, scopes, key = tok.subject or tok.client_id, tok.scopes, hashlib.sha256(tok.token.encode()).hexdigest()[:16]
    elif _stdio: (uid, scopes), key = _stdio, "stdio"
    else: raise ToolError("Não autenticado: conecte o ClipeiAki no seu Claude (OAuth) ou envie um token pessoal.")
    if scope not in scopes: raise ToolError(f"Este token não tem o escopo '{scope}'.")
    _rate(key, "read" if scope.endswith(":read") else "write")
    return uid


def run(fn, *a, **kw):
    try:
        with db.conn() as c: return fn(c, *a, **kw)
    except service.LiveError as e:
        raise ToolError(str(e))


def user_row(c, uid):
    return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def need_terms(c, uid):
    if legal.status(c, uid)["required"]:
        raise service.LiveError("Aceite a versão atual dos Termos de Uso no app do ClipeiAki antes de usar esta ação.", 428)


# ---------------------------------------------------------------- leitura (live:read)
@mcp.tool(annotations=RO)
def list_connected_streamers() -> dict:
    """Transmissões conectadas à conta (um slot do plano cada): canal, plataforma, estado (live, starting, reconnecting,
    paused, offline, error, limit, idle), tempo monitorado, momentos candidatos e cortes. Inclui slots do plano e uso do mês.
    Escopo live:read."""
    uid = principal("live:read")
    return run(lambda c: service.monitor(c, user_row(c, uid)))


@mcp.tool(annotations=RO)
def get_live_status(stream_id: str | None = None) -> dict:
    """Estado atual de uma transmissão conectada (ou de todas, sem stream_id): sessão, agente ativo, segundos gravados,
    candidatos, último evento real, uso do orçamento de IA e conexão com o Claude. Escopo live:read."""
    uid = principal("live:read")
    def go(c):
        if not stream_id: return service.monitor(c, user_row(c, uid))
        st = service.stream_out(c, service.own_stream(c, uid, stream_id))
        if st["session"]: st["session_detail"] = service.get(c, uid, st["session"]["id"], full=False)
        return st
    return run(go)


@mcp.tool(annotations=RO)
def get_live_preview(stream_id: str) -> list:
    """Último frame REAL gravado da transmissão (JPEG 480 px, extraído do bloco mais recente pelo agente) com o tempo da
    gravação (t_stream) e a idade em segundos. Não é um frame ao vivo do player: reflete o que o servidor gravou. Escopo live:read."""
    uid = principal("live:read")
    path, meta = run(lambda c: service.preview(c, uid, stream_id))
    return [meta, Image(data=path.read_bytes(), format="jpeg")]


@mcp.tool(annotations=RO)
def list_detected_moments(stream_id: str | None = None, session_id: str | None = None, status: str | None = None) -> list[dict]:
    """Momentos candidatos detectados localmente (pico de áudio, mudança de imagem, palavras de reação) com timestamps,
    sinais medidos e a decisão do Claude quando houve análise. Informe stream_id (sessão atual/última) ou session_id. Escopo live:read."""
    uid = principal("live:read")
    return run(lambda c: service.moments(c, uid, service.resolve_session(c, uid, session_id, stream_id), status))


@mcp.tool(annotations=RO)
def get_highlight(moment_id: str, include_frames: bool = True) -> list:
    """Evidências reais de um momento para você (Claude) decidir: janela, sinais medidos (áudio/imagem/palavras), transcrição
    da janela, até 3 frames JPEG do trecho (extraídos do buffer da gravação e registrados com SHA-256 como "mostrados ao
    Claude"), decisão já tomada e corte gerado. Os frames só existem enquanto o trecho está no buffer (~10–15 min). Escopo live:read."""
    uid = principal("live:read")
    def go(c):
        if include_frames: service.evidence_frames(c, uid, moment_id, 3)  # extrai do buffer se ainda não houver frames registrados
        h = service.highlight(c, uid, moment_id); imgs = []
        if include_frames:
            for f in h["frames_sent_to_claude"][:3]:
                p, _ = service.frame_path(c, uid, f["id"]); imgs.append(Image(data=p.read_bytes(), format="jpeg"))
        return [h, *imgs]
    return run(go)


@mcp.tool(annotations=RO)
def get_recent_context(session_id: str | None = None, stream_id: str | None = None, seconds: float = 120) -> dict:
    """Transcrição dos últimos segundos gravados (blocos já transcritos), com t_start e horário UTC. Escopo live:read."""
    uid = principal("live:read")
    return run(lambda c: service.recent_context(c, uid, service.resolve_session(c, uid, session_id, stream_id), seconds))


@mcp.tool(annotations=RO)
def check_channel(channel: str) -> dict:
    """Consulta na Twitch se um canal está ao vivo agora (título, categoria, qualidades). Escopo live:read."""
    uid = principal("live:read")
    try: return service.channel_status(channel, uid)
    except service.LiveError as e: raise ToolError(str(e))


# ---------------------------------------------------------------- controle (live:control)
@mcp.tool()
def connect_stream(channel: str, rights_basis: str) -> dict:
    """Conecta um canal da Twitch a um slot do plano (Creator: 3, Creator Studio: 10). rights_basis é obrigatório e
    registra a declaração do titular da conta: "owner" (sou o titular do canal) ou "authorized" (tenho autorização do
    titular). Só use com a confirmação do usuário. Escopo live:control."""
    uid = principal("live:control")
    def go(c):
        need_terms(c, uid); return service.connect_stream(c, user_row(c, uid), channel, rights_basis)
    return run(go)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True))
def remove_stream(stream_id: str) -> dict:
    """Remove uma transmissão conectada (para o monitoramento se estiver ativo e libera o slot). Cortes já gerados ficam. Escopo live:control."""
    uid = principal("live:control"); return run(lambda c: service.remove_stream(c, uid, stream_id))


@mcp.tool()
def start_monitoring(stream_id: str | None = None, channel: str | None = None, budget_usd: float | None = None,
                     max_minutes: float | None = None, lang: str = "auto") -> dict:
    """Inicia o monitoramento de uma transmissão CONECTADA (stream_id, ou channel já conectado). O backend aplica o limite
    de transmissões simultâneas do plano, a franquia mensal, a duração máxima e o orçamento de IA por sessão.
    A gravação e a análise rodam no Live Agent do servidor. Escopo live:control."""
    uid = principal("live:control")
    def go(c):
        need_terms(c, uid); u = user_row(c, uid); sid = stream_id
        if not sid:
            if not channel: raise service.LiveError("Informe stream_id ou channel.")
            r = c.execute("SELECT id FROM live_streams WHERE user_id=? AND channel=?", (uid, service.parse_channel(channel))).fetchone()
            if not r: raise service.LiveError("Canal não conectado. Use connect_stream (com a declaração de direitos) antes.", 404)
            sid = r["id"]
        return service.start_stream(c, u, sid, budget_usd, max_minutes, lang)
    return run(go)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True))
def stop_monitoring(stream_id: str | None = None, session_id: str | None = None) -> dict:
    """Para o monitoramento (pausa a transmissão conectada; o agente encerra a gravação e apaga o buffer bruto). Escopo live:control."""
    uid = principal("live:control")
    return run(lambda c: service.stop(c, uid, service.resolve_session(c, uid, session_id, stream_id)))


# ---------------------------------------------------------------- cortes (clips:*)
@mcp.tool()
def create_clip(session_id: str | None = None, stream_id: str | None = None, moment_id: str | None = None,
                start_t: float | None = None, end_t: float | None = None) -> dict:
    """Cria um corte pelo motor de render: a partir de um momento (moment_id) ou de um intervalo start_t/end_t (5–60 s,
    dentro do buffer da sessão que está gravando). Conta na franquia mensal de cortes. Escopo clips:write."""
    uid = principal("clips:write")
    if not moment_id and (start_t is None or end_t is None): raise ToolError("Informe moment_id ou start_t e end_t.")
    def go(c):
        need_terms(c, uid); sid = service.resolve_session(c, uid, session_id, stream_id)
        return service.request_clip(c, uid, sid, moment_id, start_t, end_t)
    mid = run(go)
    return {"moment_id": mid, "status": "clip_requested", "next": "Acompanhe com list_render_jobs ou get_highlight(moment_id)."}


@mcp.tool()
def approve_clip(clip_id: str) -> dict:
    """Aprova um corte já renderizado (status ready) depois da revisão do usuário; libera o download na Biblioteca. Escopo clips:write."""
    uid = principal("clips:write")
    def go(c):
        need_terms(c, uid); return service.approve_clip(c, uid, clip_id)
    return run(go)


@mcp.tool()
def review_moment(moment_id: str, decision: str, confidence: float, reason: str, start_t: float | None = None, end_t: float | None = None,
                  screen_title: str = "", title: str = "", summary: str = "") -> dict:
    """Registra a SUA decisão (Claude) sobre um momento depois de ver get_highlight. decision: "clip" (vira corte) ou "skip".
    start_t/end_t: segundos da gravação, dentro da janela do momento, corte de 5 a 60 s começando um pouco antes do gatilho.
    screen_title: até 32 caracteres em MAIÚSCULAS (texto na tela); title: título do post; reason: justificativa citando
    timestamps; summary: o que acontece. Descreva só o que os frames e a transcrição mostram. Conta na franquia de cortes.
    O usuário ainda revisa e aprova o corte antes do download. Escopo clips:write."""
    uid = principal("clips:write"); tok = get_access_token()
    def go(c):
        need_terms(c, uid)
        cname = "Claude Code (token pessoal)"
        if tok and tok.client_id != "personal-token":
            r = c.execute("SELECT info FROM oauth_clients WHERE client_id=?", (tok.client_id,)).fetchone()
            cname = oauth.client_name(json.loads(r["info"])) if r else tok.client_id
        return service.review_moment(c, uid, moment_id, decision, confidence, start_t, end_t, screen_title, title, reason, summary, cname)
    return run(go)


@mcp.prompt()
def revisar_momentos(stream_id: str = "") -> str:
    """Roteiro para o Claude revisar os momentos detectados nas lives e decidir os cortes."""
    alvo = f"a transmissão {stream_id}" if stream_id else "todas as transmissões conectadas"
    return (f"Revise os momentos detectados em {alvo} do ClipeiAki:\n"
            "1. Chame list_connected_streamers e veja quais estão ao vivo.\n"
            "2. Para cada uma, chame list_detected_moments com status 'candidate'.\n"
            "3. Para cada candidato, chame get_highlight e olhe os frames e a transcrição. Não invente o que não está neles.\n"
            "4. Decida com review_moment: 'clip' só para reação, susto, piada, jogada, briga ou revelação que funcione sozinha em 8 a 45 s;"
            " caso contrário 'skip'. Use start_t/end_t dentro da janela, começando um pouco antes do gatilho.\n"
            "5. Ao final, chame list_render_jobs e me diga quais cortes ficaram prontos para eu revisar e aprovar no app.")


@mcp.tool(annotations=RO)
def list_render_jobs(status: str | None = None, limit: int = 30) -> list[dict]:
    """Fila de renderização da conta (queued, running, done, failed) com progresso, etapa e o corte associado. Escopo clips:read."""
    uid = principal("clips:read")
    if status not in (None, "queued", "running", "done", "failed", "canceled"): raise ToolError("status inválido.")
    return run(lambda c: service.render_jobs(c, uid, status, limit))


@mcp.tool(annotations=RO)
def get_render_status(clip_id: str) -> dict:
    """Estado da renderização de um corte (fila, progresso, pronto) e links de preview/download. Escopo clips:read."""
    uid = principal("clips:read"); return run(lambda c: service.render_status(c, uid, clip_id))


def http_app():
    host = urlparse(PUBLIC_URL).hostname or "localhost"
    sec = None
    if host not in ("localhost", "127.0.0.1"):
        from mcp.server.transport_security import TransportSecuritySettings
        sec = TransportSecuritySettings(allowed_hosts=[host, f"{host}:*"], allowed_origins=[PUBLIC_URL])
    return mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True, transport_security=sec,
                                   host=host)


def main():
    global _stdio
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    db.init()
    with db.conn() as c:
        r = tokens.verify(c, os.environ.get("CLIPEIAKI_TOKEN", ""))
    if not r: sys.exit("CLIPEIAKI_TOKEN ausente ou inválido.")
    _stdio = (r[0]["id"], r[1])
    mcp.run()


if __name__ == "__main__": main()
