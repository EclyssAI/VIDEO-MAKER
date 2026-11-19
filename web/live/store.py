"""Tabelas do Live Agent. Tudo com user_id para isolamento; eventos com id crescente (SSE Last-Event-ID)."""
import json
from .. import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS live_sessions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, channel TEXT NOT NULL,
  project_id TEXT, status TEXT NOT NULL, stop_reason TEXT DEFAULT '', error TEXT DEFAULT '', lang TEXT DEFAULT 'auto',
  max_minutes REAL NOT NULL, budget_usd REAL NOT NULL, max_calls INTEGER NOT NULL, min_confidence REAL NOT NULL DEFAULT 0.6,
  spent_usd REAL NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0, recorded_s REAL NOT NULL DEFAULT 0,
  claude_state TEXT NOT NULL DEFAULT 'idle', claude_detail TEXT DEFAULT '', last_call_at REAL DEFAULT 0,
  last_analysis_id INTEGER DEFAULT 0, recorder_pgid INTEGER DEFAULT 0, recorder_host TEXT DEFAULT '', worker TEXT DEFAULT '', locked_until REAL DEFAULT 0, started_at REAL DEFAULT 0,
  stopped_at REAL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_live_sessions_user ON live_sessions(user_id, created_at);
CREATE TABLE IF NOT EXISTS live_segments (
  session_id TEXT NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE, user_id TEXT NOT NULL, seq INTEGER NOT NULL,
  path TEXT NOT NULL, t_start REAL NOT NULL, duration REAL NOT NULL, wall_start REAL NOT NULL, db_max REAL, db_median REAL,
  vis_max REAL, text TEXT DEFAULT '', words TEXT DEFAULT '[]', deleted INTEGER DEFAULT 0, created_at REAL NOT NULL,
  PRIMARY KEY (session_id, seq), UNIQUE (session_id, path));
CREATE TABLE IF NOT EXISTS live_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL, kind TEXT NOT NULL, t_stream REAL, wall_at REAL NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_live_events ON live_events(session_id, id);
CREATE TABLE IF NOT EXISTS live_moments (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE, user_id TEXT NOT NULL,
  peak REAL NOT NULL, w_start REAL NOT NULL, w_end REAL NOT NULL, score REAL NOT NULL, signals TEXT NOT NULL,
  status TEXT NOT NULL, decision TEXT DEFAULT '', clip_id TEXT DEFAULT '', source TEXT DEFAULT '', error TEXT DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_live_moments ON live_moments(session_id, peak);
CREATE TABLE IF NOT EXISTS live_frames (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE, user_id TEXT NOT NULL,
  moment_id TEXT, t_stream REAL NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, sent_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS live_streams (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, platform TEXT NOT NULL DEFAULT 'twitch',
  channel TEXT NOT NULL, display_name TEXT DEFAULT '', slot INTEGER NOT NULL, rights_basis TEXT NOT NULL,
  rights_attested_at REAL NOT NULL, current_session_id TEXT DEFAULT '', last_check TEXT DEFAULT '', last_checked_at REAL DEFAULT 0,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE (user_id, platform, channel), UNIQUE (user_id, slot));
CREATE INDEX IF NOT EXISTS ix_live_streams_user ON live_streams(user_id, slot);
CREATE TABLE IF NOT EXISTS api_tokens (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL,
  token_hash TEXT UNIQUE NOT NULL, scopes TEXT NOT NULL, created_at REAL NOT NULL, last_used_at REAL DEFAULT 0,
  revoked INTEGER DEFAULT 0);
"""

ACTIVE = ("starting", "running", "reconnecting", "stopping")


def session_dir(uid, sid): return db.user_dir(uid) / "live" / sid
def preview_path(uid, sid): return session_dir(uid, sid) / "preview.jpg"


def event(c, s, kind, data, t_stream=None):
    cur = c.execute("INSERT INTO live_events(session_id,user_id,kind,t_stream,wall_at,data) VALUES(?,?,?,?,?,?)",
                    (s["id"], s["user_id"], kind, t_stream, db.now(), json.dumps(data, ensure_ascii=False)))
    return cur.lastrowid


def get_session(c, uid, sid):
    return c.execute("SELECT * FROM live_sessions WHERE id=? AND user_id=?", (sid, uid)).fetchone()


def update_session(c, sid, **kw):
    kw["updated_at"] = db.now()
    c.execute(f"UPDATE live_sessions SET {', '.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), sid))
