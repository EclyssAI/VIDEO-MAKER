"""Servidor de autorização OAuth 2.1 do ClipeiAki para conectar o Claude do CLIENTE ao MCP (conector personalizado do
claude.ai / Claude Desktop / Claude Code). Implementa o provider do SDK MCP oficial (rotas /authorize, /token, /register,
/revoke e metadados RFC 8414/9728 são do SDK). Padrão: registro dinâmico de cliente (RFC 7591, cliente público), PKCE S256
obrigatório, consentimento explícito do usuário logado, código de uso único (5 min), access token de 1 h e refresh token
de 30 dias com rotação. Tokens pessoais (cak_…) continuam aceitos para quem prefere colar um token no Claude Code.

Guardamos só hashes SHA-256 de códigos e tokens. O consentimento mostra o nome do cliente e o domínio de retorno."""
import asyncio, hashlib, json, os, secrets, threading, time
from urllib.parse import urlencode, urlparse
from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError, RefreshToken,
                                      RegistrationError, TokenError)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from . import db, tokens

PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
RESOURCE = f"{PUBLIC_URL}/mcp"  # único recurso protegido por este servidor de autorização
SCOPES = list(tokens.SCOPES)
ACCESS_TTL, REFRESH_TTL, CODE_TTL, REQUEST_TTL = 3600, 30 * 86400, 300, 600
TRUSTED_HOSTS = {"claude.ai", "claude.com", "www.claude.ai", "localhost", "127.0.0.1"}  # retorno exibido como "verificado"
REG_PER_HOUR = int(os.environ.get("OAUTH_REGISTRATIONS_PER_HOUR", "60"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_clients (client_id TEXT PRIMARY KEY, info TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_requests (id TEXT PRIMARY KEY, client_id TEXT NOT NULL, params TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_codes (code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  scopes TEXT NOT NULL, code_challenge TEXT NOT NULL, redirect_uri TEXT NOT NULL, redirect_explicit INTEGER NOT NULL, resource TEXT, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_tokens (token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL, family TEXT NOT NULL, client_id TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, scopes TEXT NOT NULL, resource TEXT, expires_at REAL NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, last_used_at REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_oauth_tokens_user ON oauth_tokens(user_id, family);
"""
_reg, _reg_lock = [], threading.Lock()


def _h(v): return hashlib.sha256(v.encode()).hexdigest()


def _run(fn):
    def go():
        with db.conn() as c: return fn(c)
    return asyncio.to_thread(go)


def client_name(info):
    return (info.get("client_name") or "Aplicativo sem nome")[:80]


class Provider:
    # ---------------- clientes (registro dinâmico) ----------------
    async def get_client(self, client_id):
        r = await _run(lambda c: c.execute("SELECT info FROM oauth_clients WHERE client_id=?", (client_id,)).fetchone())
        return OAuthClientInformationFull.model_validate_json(r["info"]) if r else None

    async def register_client(self, client_info):
        now = time.time()
        with _reg_lock:
            _reg[:] = [t for t in _reg if now - t < 3600]
            if len(_reg) >= REG_PER_HOUR:
                raise RegistrationError(error="invalid_client_metadata", error_description="Muitos registros de clientes. Tente mais tarde.")
            _reg.append(now)
        for u in client_info.redirect_uris or []:
            p = urlparse(str(u))
            if p.scheme not in ("https", "http") or (p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1")):
                raise RegistrationError(error="invalid_redirect_uri", error_description="redirect_uri precisa ser HTTPS (ou http://localhost).")
        await _run(lambda c: c.execute("INSERT INTO oauth_clients(client_id, info, created_at) VALUES(?,?,?)",
                                       (client_info.client_id, client_info.model_dump_json(), now)))

    # ---------------- autorização: guarda o pedido e manda o usuário para a tela de consentimento ----------------
    async def authorize(self, client, params: AuthorizationParams):
        rid = secrets.token_urlsafe(24)
        data = {"state": params.state, "scopes": params.scopes, "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri), "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "resource": params.resource}
        await _run(lambda c: (c.execute("DELETE FROM oauth_requests WHERE expires_at<?", (time.time(),)),
                              c.execute("INSERT INTO oauth_requests VALUES(?,?,?,?)", (rid, client.client_id, json.dumps(data), time.time() + REQUEST_TTL))))
        return f"{PUBLIC_URL}/conectar-claude?req={rid}"

    async def load_authorization_code(self, client, authorization_code):
        r = await _run(lambda c: c.execute("SELECT * FROM oauth_codes WHERE code_hash=? AND client_id=?", (_h(authorization_code), client.client_id)).fetchone())
        if not r or r["expires_at"] < time.time(): return None
        return AuthorizationCode(code=authorization_code, scopes=json.loads(r["scopes"]), expires_at=r["expires_at"], client_id=r["client_id"],
                                 code_challenge=r["code_challenge"], redirect_uri=r["redirect_uri"],
                                 redirect_uri_provided_explicitly=bool(r["redirect_explicit"]), resource=r["resource"], subject=r["user_id"])

    async def exchange_authorization_code(self, client, authorization_code):
        def go(c):
            c.execute("BEGIN IMMEDIATE")
            try:
                n = c.execute("DELETE FROM oauth_codes WHERE code_hash=? AND client_id=?", (_h(authorization_code.code), client.client_id)).rowcount
                if not n: raise TokenError(error="invalid_grant", error_description="Código já usado ou inválido.")
                out = _issue(c, client.client_id, authorization_code.subject, authorization_code.scopes, authorization_code.resource, secrets.token_hex(8))
                c.execute("COMMIT"); return out
            except Exception:
                c.execute("ROLLBACK"); raise
        return await _run(go)

    # ---------------- refresh (com rotação) ----------------
    async def load_refresh_token(self, client, refresh_token):
        r = await _run(lambda c: c.execute("SELECT * FROM oauth_tokens WHERE token_hash=? AND kind='refresh' AND client_id=? AND revoked=0",
                                           (_h(refresh_token), client.client_id)).fetchone())
        if not r or r["expires_at"] < time.time(): return None
        return RefreshToken(token=refresh_token, client_id=r["client_id"], scopes=json.loads(r["scopes"]), expires_at=int(r["expires_at"]),
                            resource=r["resource"], subject=r["user_id"])

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        def go(c):
            c.execute("BEGIN IMMEDIATE")
            try:
                r = c.execute("SELECT * FROM oauth_tokens WHERE token_hash=? AND kind='refresh' AND revoked=0", (_h(refresh_token.token),)).fetchone()
                if not r: raise TokenError(error="invalid_grant", error_description="Refresh token inválido.")
                want = scopes or json.loads(r["scopes"])
                if not set(want) <= set(json.loads(r["scopes"])): raise TokenError(error="invalid_scope", error_description="Escopo maior que o autorizado.")
                c.execute("UPDATE oauth_tokens SET revoked=1 WHERE family=?", (r["family"],))  # rotação: o par antigo deixa de valer
                out = _issue(c, client.client_id, r["user_id"], want, r["resource"], r["family"])
                c.execute("COMMIT"); return out
            except Exception:
                c.execute("ROLLBACK"); raise
        return await _run(go)

    # ---------------- validação de token no /mcp (OAuth ou token pessoal) ----------------
    async def load_access_token(self, token):
        def go(c):
            if token.startswith(tokens.PREFIX):
                v = tokens.verify(c, token)
                return AccessToken(token=token, client_id="personal-token", scopes=v[1], subject=v[0]["id"], resource=RESOURCE) if v else None
            r = c.execute("SELECT * FROM oauth_tokens WHERE token_hash=? AND kind='access' AND revoked=0", (_h(token),)).fetchone()
            if not r or r["expires_at"] < time.time(): return None
            c.execute("UPDATE oauth_tokens SET last_used_at=? WHERE token_hash=?", (time.time(), r["token_hash"]))
            return AccessToken(token=token, client_id=r["client_id"], scopes=json.loads(r["scopes"]), expires_at=int(r["expires_at"]),
                               resource=r["resource"], subject=r["user_id"])
        return await _run(go)

    async def revoke_token(self, token):
        await _run(lambda c: c.execute("UPDATE oauth_tokens SET revoked=1 WHERE family=(SELECT family FROM oauth_tokens WHERE token_hash=?)",
                                       (_h(token.token),)))

    async def exchange_identity_assertion(self, client, params):
        raise TokenError(error="unsupported_grant_type", error_description="Não suportado.")


def _issue(c, client_id, user_id, scopes, resource, family):
    resource = resource or RESOURCE  # sem indicador RFC 8707 do cliente: o token vale só para o /mcp do ClipeiAki
    at, rt, now = "cao_" + secrets.token_urlsafe(32), "car_" + secrets.token_urlsafe(32), time.time()
    for tok, kind, ttl in ((at, "access", ACCESS_TTL), (rt, "refresh", REFRESH_TTL)):
        c.execute("INSERT INTO oauth_tokens(token_hash,kind,family,client_id,user_id,scopes,resource,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (_h(tok), kind, family, client_id, user_id, json.dumps(scopes), resource, now + ttl, now))
    return OAuthToken(access_token=at, token_type="Bearer", expires_in=ACCESS_TTL, scope=" ".join(scopes), refresh_token=rt)


# ---------------- tela de consentimento (chamada pela API web do usuário logado) ----------------
def pending(c, rid):
    r = c.execute("SELECT r.*, k.info FROM oauth_requests r JOIN oauth_clients k ON k.client_id=r.client_id WHERE r.id=? AND r.expires_at>?",
                  (rid, time.time())).fetchone()
    if not r: return None
    p, info = json.loads(r["params"]), json.loads(r["info"])
    host = urlparse(p["redirect_uri"]).hostname or ""
    scopes = [s for s in (p["scopes"] or SCOPES) if s in tokens.SCOPES] or SCOPES
    return {"client_id": r["client_id"], "client_name": client_name(info), "redirect_host": host, "verified_host": host in TRUSTED_HOSTS,
            "scopes": [{"scope": s, "description": tokens.SCOPES[s]} for s in scopes], "params": p}


def decide(c, rid, uid, approve):
    req = pending(c, rid)
    if not req: return None
    p = req["params"]; c.execute("DELETE FROM oauth_requests WHERE id=?", (rid,))
    q = {"state": p["state"]} if p.get("state") else {}
    if not approve:
        return p["redirect_uri"] + ("&" if "?" in p["redirect_uri"] else "?") + urlencode({"error": "access_denied", **q})
    code = secrets.token_urlsafe(32)
    c.execute("INSERT INTO oauth_codes VALUES(?,?,?,?,?,?,?,?,?)", (_h(code), req["client_id"], uid, json.dumps([s["scope"] for s in req["scopes"]]),
              p["code_challenge"], p["redirect_uri"], int(p["redirect_uri_provided_explicitly"]), p.get("resource"), time.time() + CODE_TTL))
    return p["redirect_uri"] + ("&" if "?" in p["redirect_uri"] else "?") + urlencode({"code": code, **q})


def connections(c, uid):
    rows = c.execute("""SELECT t.family, t.client_id, k.info, MIN(t.created_at) AS created_at, MAX(t.last_used_at) AS last_used_at,
                        MAX(t.expires_at) AS expires_at, t.scopes FROM oauth_tokens t LEFT JOIN oauth_clients k ON k.client_id=t.client_id
                        WHERE t.user_id=? AND t.revoked=0 AND t.expires_at>? GROUP BY t.family ORDER BY created_at DESC""", (uid, time.time())).fetchall()
    return [{"id": r["family"], "client_name": client_name(json.loads(r["info"] or "{}")), "scopes": json.loads(r["scopes"]),
             "created_at": r["created_at"], "last_used_at": r["last_used_at"] or None} for r in rows]


def disconnect(c, uid, family):
    return c.execute("UPDATE oauth_tokens SET revoked=1 WHERE user_id=? AND family=?", (uid, family)).rowcount


def last_use(c, uid):
    a = c.execute("SELECT MAX(last_used_at) FROM oauth_tokens WHERE user_id=?", (uid,)).fetchone()[0] or 0
    b = c.execute("SELECT MAX(last_used_at) FROM api_tokens WHERE user_id=? AND revoked=0", (uid,)).fetchone()[0] or 0
    return max(a, b) or None
