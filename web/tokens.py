"""Tokens pessoais de API (usados pelo MCP). Guardamos só o SHA-256; o token aparece uma única vez na criação."""
import hashlib, json, secrets
from . import db

SCOPES = {"live:read": "Consultar lives, sessões, contexto e momentos",
          "live:control": "Iniciar e parar monitoramento",
          "clips:read": "Ver cortes e renderizações",
          "clips:write": "Criar cortes"}
PREFIX = "cak_"


def _h(t): return hashlib.sha256(t.encode()).hexdigest()


DEFAULT_DAYS, MAX_DAYS = 90, 365


def create(c, uid, name, scopes, days=None):
    scopes = sorted(set(scopes) & SCOPES.keys())
    if not scopes: raise ValueError("Escolha pelo menos um escopo.")
    try: days = int(days if days not in (None, "") else DEFAULT_DAYS)
    except (TypeError, ValueError): raise ValueError("Validade inválida.")
    if not 1 <= days <= MAX_DAYS: raise ValueError(f"A validade precisa ficar entre 1 e {MAX_DAYS} dias.")
    if c.execute("SELECT COUNT(*) FROM api_tokens WHERE user_id=? AND revoked=0", (uid,)).fetchone()[0] >= 10:
        raise ValueError("Limite de 10 tokens ativos.")
    tok = PREFIX + secrets.token_urlsafe(32); tid = db.new_id("tok")
    c.execute("INSERT INTO api_tokens(id,user_id,name,token_hash,scopes,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
              (tid, uid, (name or "MCP")[:60], _h(tok), json.dumps(scopes), db.now(), db.now() + days * 86400))
    return tid, tok, scopes


def verify(c, token):
    """Retorna (user, scopes) ou None."""
    if not token or not token.startswith(PREFIX): return None
    # expires_at=0: token criado antes da expiração existir (aparece como "sem expiração" na conta; revogue e recrie)
    r = c.execute("SELECT t.id AS tid, t.scopes, u.* FROM api_tokens t JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.revoked=0 "
                  "AND (t.expires_at=0 OR t.expires_at>?)", (_h(token), db.now())).fetchone()
    if not r: return None
    c.execute("UPDATE api_tokens SET last_used_at=? WHERE id=?", (db.now(), r["tid"]))
    return r, json.loads(r["scopes"])


def list_(c, uid):
    return [{"id": r["id"], "name": r["name"], "scopes": json.loads(r["scopes"]), "created_at": r["created_at"],
             "last_used_at": r["last_used_at"] or None, "expires_at": r["expires_at"] or None, "expired": bool(r["expires_at"]) and r["expires_at"] <= db.now()}
            for r in c.execute("SELECT * FROM api_tokens WHERE user_id=? AND revoked=0 ORDER BY created_at DESC", (uid,))]


def revoke(c, uid, tid):
    return c.execute("UPDATE api_tokens SET revoked=1 WHERE id=? AND user_id=?", (tid, uid)).rowcount
