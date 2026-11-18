"""ClipeiAki Live MCP — servidor MCP oficial (SDK Python v2, MCPServer).
Controla o Live Agent e o motor existentes pelas MESMAS funções da API web (web/live/service.py): não há lógica de
captura ou edição duplicada aqui.

Autenticação: token pessoal (Conta → Tokens de API), enviado como `Authorization: Bearer cak_...` no transporte HTTP
(/mcp) ou na variável CLIPEIAKI_TOKEN no modo stdio. Cada ferramenta exige um escopo:
live:read, live:control, clips:read, clips:write. Todas as consultas são filtradas pelo dono do token.

  HTTP:  servido pelo app web em <PUBLIC_URL>/mcp
  stdio: CLIPEIAKI_TOKEN=cak_... VM_DATA_DIR=... python -m web.mcp_server"""
import asyncio, json, logging, os, sys
from urllib.parse import urlparse
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.types import ToolAnnotations
from . import db, tokens
from .live import service

log = logging.getLogger("mcp")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
VERSION = "0.1.0"
_stdio = None  # (user_id, scopes) quando rodando por stdio


class TokenVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        def check():
            with db.conn() as c: return tokens.verify(c, token)
        r = await asyncio.to_thread(check)
        if not r: return None
        user, scopes = r
        return AccessToken(token=token, client_id=user["id"], subject=user["id"], scopes=scopes, expires_at=None,
                           resource=f"{PUBLIC_URL}/mcp")


mcp = MCPServer(
    "ClipeiAki Live MCP", version=VERSION,
    instructions="Controla o Claude Live Agent do ClipeiAki: consulta canais da Twitch, inicia/para o monitoramento, lê o "
                 "contexto recente (transcrição com timestamps), lista momentos detectados e as decisões do Claude, cria cortes "
                 "pelo motor de render e acompanha a renderização. Timestamps t_* são segundos da gravação da sessão.",
    token_verifier=TokenVerifier(),
    auth=AuthSettings(issuer_url=PUBLIC_URL, resource_server_url=f"{PUBLIC_URL}/mcp", required_scopes=None,
                      validate_token_resource=True))

RO = ToolAnnotations(read_only_hint=True)


def principal(scope: str) -> str:
    tok = get_access_token()
    if tok: uid, scopes = tok.client_id, tok.scopes
    elif _stdio: uid, scopes = _stdio
    else: raise ToolError("Não autenticado: envie um token pessoal do ClipeiAki.")
    if scope not in scopes: raise ToolError(f"Este token não tem o escopo '{scope}'.")
    return uid


def run(fn, *a, **kw):
    try:
        with db.conn() as c: return fn(c, *a, **kw)
    except service.LiveError as e:
        raise ToolError(str(e))


@mcp.tool(annotations=RO)
def check_channel(channel: str) -> dict:
    """Consulta na Twitch se um canal está ao vivo agora (título, categoria, qualidades). Escopo live:read."""
    uid = principal("live:read")
    try: return service.channel_status(channel, uid)
    except service.LiveError as e: raise ToolError(str(e))


@mcp.tool(annotations=RO)
def list_sessions(limit: int = 20) -> list[dict]:
    """Lista suas sessões de monitoramento (mais recentes primeiro), com estado, custo e conexão com o Claude. Escopo live:read."""
    uid = principal("live:read"); return run(lambda c: service.list_sessions(c, uid, max(1, min(limit, 100))))


@mcp.tool(annotations=RO)
def get_session(session_id: str) -> dict:
    """Detalhes de uma sessão: estado, orçamento gasto, última análise do Claude (com frames enviados) e momentos. Escopo live:read."""
    uid = principal("live:read"); return run(lambda c: service.get(c, uid, session_id))


@mcp.tool()
def start_monitoring(channel: str, budget_usd: float | None = None, max_minutes: float | None = None, lang: str = "auto") -> dict:
    """Inicia o monitoramento contínuo de um canal da Twitch (um canal por sessão). O orçamento de IA e a duração são
    limitados pelo plano. A gravação e a análise rodam no Live Agent do servidor. Escopo live:control."""
    uid = principal("live:control")
    def go(c):
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return service.start(c, u, channel, budget_usd, max_minutes, lang)
    return run(go)


@mcp.tool(annotations=ToolAnnotations(destructive_hint=True))
def stop_monitoring(session_id: str) -> dict:
    """Para uma sessão de monitoramento (o agente termina a gravação e libera o buffer). Escopo live:control."""
    uid = principal("live:control"); return run(lambda c: service.stop(c, uid, session_id))


@mcp.tool(annotations=RO)
def get_recent_context(session_id: str, seconds: float = 120) -> dict:
    """Transcrição dos últimos segundos gravados, por segmento, com t_start (segundos da sessão) e horário UTC. Escopo live:read."""
    uid = principal("live:read"); return run(lambda c: service.recent_context(c, uid, session_id, seconds))


@mcp.tool(annotations=RO)
def list_moments(session_id: str, status: str | None = None) -> list[dict]:
    """Momentos candidatos detectados (áudio/imagem/palavras) e a decisão do Claude quando houve análise. Escopo live:read."""
    uid = principal("live:read"); return run(lambda c: service.moments(c, uid, session_id, status))


@mcp.tool()
def create_clip(session_id: str, moment_id: str | None = None, start_t: float | None = None, end_t: float | None = None) -> dict:
    """Cria um corte pelo motor de render: a partir de um momento (moment_id) ou de um intervalo start_t/end_t (5–60 s,
    dentro do buffer da sessão). Escopo clips:write."""
    uid = principal("clips:write")
    if not moment_id and (start_t is None or end_t is None): raise ToolError("Informe moment_id ou start_t e end_t.")
    mid = run(lambda c: service.request_clip(c, uid, session_id, moment_id, start_t, end_t))
    return {"moment_id": mid, "status": "clip_requested", "next": "Acompanhe com list_moments ou get_render_status quando houver clip_id."}


@mcp.tool(annotations=RO)
def get_render_status(clip_id: str) -> dict:
    """Estado da renderização de um corte (fila, progresso, pronto) e links de preview/download. Escopo clips:read."""
    uid = principal("clips:read"); return run(lambda c: service.render_status(c, uid, clip_id))


@mcp.tool(annotations=RO)
def list_clips(session_id: str) -> list[dict]:
    """Cortes gerados a partir de uma sessão de live. Escopo clips:read."""
    uid = principal("clips:read")
    def go(c):
        s = c.execute("SELECT project_id FROM live_sessions WHERE id=? AND user_id=?", (session_id, uid)).fetchone()
        if not s: raise service.LiveError("Sessão não encontrada.", 404)
        return [service.render_status(c, uid, r["id"]) for r in c.execute("SELECT id FROM clips WHERE project_id=? AND user_id=? ORDER BY idx",
                                                                          (s["project_id"], uid))]
    return run(go)


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
