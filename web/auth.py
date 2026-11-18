"""Autenticação: senha com scrypt (stdlib), sessão opaca em cookie HttpOnly (hash SHA-256 no banco),
limite de tentativas de login em memória por IP+e-mail."""
import hashlib, hmac, os, secrets, time, collections, re
from . import db

SESSION_DAYS = 30
COOKIE = "vm_session"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_fails = collections.defaultdict(list)


def hash_pw(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_pw(pw, stored):
    try:
        _, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got.hex(), h)
    except Exception:
        return False


def _th(token): return hashlib.sha256(token.encode()).hexdigest()


def create_session(c, uid):
    token = secrets.token_urlsafe(32); t = db.now()
    c.execute("INSERT INTO sessions VALUES(?,?,?,?)", (_th(token), uid, t, t + SESSION_DAYS * 86400))
    return token


def user_from_token(c, token):
    if not token: return None
    r = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                  (_th(token), db.now())).fetchone()
    return r


def destroy_session(c, token):
    if token: c.execute("DELETE FROM sessions WHERE token_hash=?", (_th(token),))


def throttled(key, limit=8, window=900):
    t = time.time(); _fails[key] = [x for x in _fails[key] if t - x < window]
    return len(_fails[key]) >= limit


def record_fail(key): _fails[key].append(time.time())


def valid_password(pw): return isinstance(pw, str) and 8 <= len(pw) <= 200
def valid_email(e): return isinstance(e, str) and bool(EMAIL_RE.match(e))
def secure_cookies(): return os.environ.get("COOKIE_SECURE", "1") == "1"
