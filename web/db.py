"""Persistência (SQLite, WAL). Uma conexão por thread/uso; todas as consultas de dados de cliente filtram por user_id."""
import os, sqlite3, pathlib, time, secrets, contextlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = pathlib.Path(os.environ.get("VM_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = DATA / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, name TEXT DEFAULT '',
  handle TEXT DEFAULT '', plan TEXT NOT NULL DEFAULT 'none', plan_status TEXT NOT NULL DEFAULT 'none',
  plan_until REAL DEFAULT 0, created_at REAL NOT NULL);
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
  start REAL, end REAL, peak REAL, strength REAL, data TEXT NOT NULL, copy TEXT NOT NULL,
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
"""


def now(): return time.time()
def new_id(prefix): return f"{prefix}_{secrets.token_urlsafe(12)}"


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA busy_timeout=30000")
    return c


def init():
    with contextlib.closing(connect()) as c: c.executescript(SCHEMA)


@contextlib.contextmanager
def conn():
    c = connect()
    try: yield c
    finally: c.close()


def user_dir(uid): return DATA / "users" / uid
def month(): return time.strftime("%Y-%m", time.gmtime())
