"""Persistência (SQLite, WAL). Uma conexão por thread/uso; todas as consultas de dados de cliente filtram por user_id."""
import os, sqlite3, pathlib, time, secrets, contextlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = pathlib.Path(os.environ.get("VM_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = DATA / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, name TEXT DEFAULT '',
  handle TEXT DEFAULT '', plan TEXT NOT NULL DEFAULT 'none', plan_status TEXT NOT NULL DEFAULT 'none',
  plan_until REAL DEFAULT 0, email_verified INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at REAL NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL,
  source_file TEXT, source_name TEXT, duration REAL DEFAULT 0, lang TEXT DEFAULT 'auto', status TEXT NOT NULL,
  error TEXT DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_projects_user ON projects(user_id, created_at);
CREATE TABLE IF NOT EXISTS clips (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, idx INTEGER NOT NULL,
  start REAL, "end" REAL, peak REAL, strength REAL, data TEXT NOT NULL, copy TEXT NOT NULL,
  status TEXT NOT NULL, video_path TEXT DEFAULT '', thumb_path TEXT DEFAULT '', error TEXT DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_clips_user ON clips(user_id, status);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, project_id TEXT, clip_id TEXT, type TEXT NOT NULL,
  status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
  progress REAL DEFAULT 0, stage TEXT DEFAULT '', error TEXT DEFAULT '', locked_until REAL DEFAULT 0,
  worker TEXT DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status, created_at);
CREATE TABLE IF NOT EXISTS usage (
  user_id TEXT NOT NULL, month TEXT NOT NULL, projects INTEGER DEFAULT 0, minutes REAL DEFAULT 0,
  PRIMARY KEY (user_id, month));
CREATE TABLE IF NOT EXISTS billing_events (
  id TEXT PRIMARY KEY, event TEXT NOT NULL, email TEXT, offer_id TEXT, plan TEXT, applied INTEGER DEFAULT 0,
  raw TEXT, received_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS entitlements (
  email TEXT PRIMARY KEY, plan TEXT NOT NULL, status TEXT NOT NULL, until REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS terms_acceptances (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  terms_version TEXT NOT NULL, privacy_version TEXT NOT NULL, accepted_at REAL NOT NULL, context TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_terms_user ON terms_acceptances(user_id, accepted_at);
CREATE TABLE IF NOT EXISTS access_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ip TEXT NOT NULL, event TEXT NOT NULL, at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_access_at ON access_logs(at);
"""
ACCESS_LOG_DAYS = 183  # Marco Civil da Internet (Lei 12.965/2014), art. 15: 6 meses


def log_access(c, uid, ip, event):
    """Registro de acesso a aplicação (IP + data/hora). Sem FK: deve sobreviver à exclusão da conta pelo prazo legal."""
    c.execute("INSERT INTO access_logs(user_id, ip, event, at) VALUES(?,?,?,?)", (uid, ip or "", event, now()))
    c.execute("DELETE FROM access_logs WHERE at < ?", (now() - ACCESS_LOG_DAYS * 86400,))

# Colunas adicionadas depois da primeira versão: bancos existentes recebem ALTER TABLE (idempotente, sem perder dados).
MIGRATIONS = {
    "usage": {"live_s": "REAL NOT NULL DEFAULT 0", "live_clips": "INTEGER NOT NULL DEFAULT 0", "ai_usd": "REAL NOT NULL DEFAULT 0"},
    "api_tokens": {"expires_at": "REAL NOT NULL DEFAULT 0"},
    "live_sessions": {"stream_id": "TEXT DEFAULT ''", "preview_t": "REAL DEFAULT 0", "preview_wall": "REAL DEFAULT 0",
                      "transcribe_mode": "TEXT NOT NULL DEFAULT 'events'"},
    "live_segments": {"transcribed": "INTEGER NOT NULL DEFAULT 1"},
}


def migrate(c):
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols.items():
            if col not in have: c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def now(): return time.time()
def new_id(prefix): return f"{prefix}_{secrets.token_urlsafe(12)}"


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA busy_timeout=30000")
    return c


def init():
    from .live.store import SCHEMA as LIVE_SCHEMA
    from .oauth import SCHEMA as OAUTH_SCHEMA
    with contextlib.closing(connect()) as c:
        c.executescript(SCHEMA + LIVE_SCHEMA + OAUTH_SCHEMA); migrate(c)
        c.execute("CREATE INDEX IF NOT EXISTS ix_live_sessions_stream ON live_sessions(stream_id, created_at)")


@contextlib.contextmanager
def conn():
    c = connect()
    try: yield c
    finally: c.close()


def user_dir(uid): return DATA / "users" / uid
def month(): return time.strftime("%Y-%m", time.gmtime())
