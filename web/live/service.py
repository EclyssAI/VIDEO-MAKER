"""Operações do Live Agent compartilhadas pela API REST e pelo servidor MCP (uma única implementação).
Todas recebem user_id e filtram por ele: um usuário nunca enxerga sessão, momento, frame ou corte de outro."""
import json, math, os, re, subprocess, threading, time
from .. import db, plans
from . import store, claude_live

CHANNEL_RE = re.compile(r"^(?:https?://)?(?:www\.|m\.)?twitch\.tv/([A-Za-z0-9_]{3,25})/?(?:\?.*)?$|^([A-Za-z0-9_]{3,25})$")


class LiveError(Exception):
    def __init__(self, msg, code=400): super().__init__(msg); self.code = code


def parse_channel(s):
    m = CHANNEL_RE.match((s or "").strip())
    if not m: raise LiveError("Informe um canal da Twitch (ex.: twitch.tv/canal).")
    return (m.group(1) or m.group(2)).lower()


_cache, _cache_lock = {}, threading.Lock()
_streamlink_slots = threading.BoundedSemaphore(int(os.environ.get("LIVE_CHECK_CONCURRENCY", "3")))
_user_checks = {}


def num(v, name):
    try: x = float(v)
    except (TypeError, ValueError): raise LiveError(f"{name} inválido.")
    if not math.isfinite(x): raise LiveError(f"{name} inválido.")
    return x


def channel_status(channel, uid=None):
    """Consulta real à Twitch via streamlink (sem baixar vídeo). Cache de 30 s por canal, no máximo 3 consultas
    simultâneas no servidor e 10 por minuto por usuário."""
    ch = parse_channel(channel); now = time.time()
    with _cache_lock:
        hit = _cache.get(ch)
        if hit and now - hit["checked_at"] < 30: return hit
        if uid:
            v = [t for t in _user_checks.get(uid, []) if now - t < 60]
            if len(v) >= 10: raise LiveError("Muitas consultas seguidas. Aguarde um minuto.", 429)
            _user_checks[uid] = v + [now]
    if not _streamlink_slots.acquire(timeout=20): raise LiveError("Servidor ocupado consultando a Twitch. Tente de novo.", 503)
    try:
        out = _query(ch)
    finally:
        _streamlink_slots.release()
    with _cache_lock:
        _cache[ch] = out
        if len(_cache) > 5000: _cache.clear()
    return out


def _query(ch):
    try:
        r = subprocess.run(["streamlink", "--json", f"https://www.twitch.tv/{ch}"], capture_output=True, text=True, timeout=30)
        j = json.loads(r.stdout or "{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return {"channel": ch, "live": False, "error": "Não foi possível consultar a Twitch agora.", "checked_at": time.time()}
    md = j.get("metadata") or {}
    return {"channel": ch, "live": bool(j.get("streams")), "title": md.get("title"), "author": md.get("author"),
            "category": md.get("category"), "qualities": sorted((j.get("streams") or {}).keys())[:8], "checked_at": time.time()}


def limits_for(user):
    L = plans.limits(plans.effective_plan(user))
    if not L: raise LiveError("Sua conta não tem um plano ativo.", 402)
    return L


def start(c, user, channel, budget_usd=None, max_minutes=None, lang="auto", min_confidence=0.6):
    L = limits_for(user); ch = parse_channel(channel)
    if lang not in ("auto", "pt", "en", "es"): raise LiveError("Idioma inválido.")
    if c.execute(f"SELECT 1 FROM live_sessions WHERE user_id=? AND status IN {store.ACTIVE}", (user["id"],)).fetchone():
        raise LiveError("Você já tem uma sessão ao vivo ativa. Pare a atual antes de iniciar outra.", 409)
    u = plans.usage(c, user["id"])
    if u["minutes"] >= L["minutes_per_month"]: raise LiveError("Seus minutos do mês acabaram.", 402)
    budget = min(num(budget_usd if budget_usd is not None else L["live_budget_usd_max"], "Orçamento"), L["live_budget_usd_max"])
    minutes = min(num(max_minutes if max_minutes is not None else L["live_max_minutes"], "Duração"), L["live_max_minutes"],
                  L["minutes_per_month"] - u["minutes"])
    if budget < 0 or minutes < 1: raise LiveError("Orçamento ou duração inválidos.")
    t = db.now(); sid = db.new_id("live"); pid = db.new_id("prj")
    c.execute("INSERT INTO projects(id,user_id,name,source_name,lang,status,created_at,updated_at) VALUES(?,?,?,?,?,'live',?,?)",
              (pid, user["id"], f"Live · {ch} · {time.strftime('%d/%m %H:%M', time.gmtime(t - 3 * 3600))}", f"twitch.tv/{ch}", lang, t, t))
    c.execute("INSERT INTO live_sessions(id,user_id,channel,project_id,status,lang,max_minutes,budget_usd,max_calls,min_confidence,"
              "created_at,updated_at) VALUES(?,?,?,?,'starting',?,?,?,?,?,?,?)",
              (sid, user["id"], ch, pid, lang, minutes, budget, int(L["live_max_calls"]), min(max(num(min_confidence, "Confiança"), 0), 1), t, t))
    s = store.get_session(c, user["id"], sid)
    store.event(c, s, "created", {"channel": ch, "budget_usd": budget, "max_minutes": minutes, "max_calls": int(L["live_max_calls"]),
                                  "claude": claude_live.status()[0]}, 0)
    return session_out(c, s)


def stop(c, uid, sid):
    s = store.get_session(c, uid, sid)
    if not s: raise LiveError("Sessão não encontrada.", 404)
    if s["status"] in ("starting", "running", "reconnecting"):
        store.update_session(c, sid, status="stopping", stop_reason="user")
        store.event(c, s, "stop_requested", {"by": "user"}, s["recorded_s"])
    return session_out(c, store.get_session(c, uid, sid))


def session_out(c, s, full=False):
    st, detail = claude_live.status()
    claude = {"configured": st == "ready", "state": s["claude_state"] if st == "ready" else "disabled",
              "detail": s["claude_detail"] if st == "ready" and s["claude_detail"] else detail, "last_call_at": s["last_call_at"] or None}
    last = None
    if s["last_analysis_id"]:
        ev = c.execute("SELECT * FROM live_events WHERE id=? AND user_id=?", (s["last_analysis_id"], s["user_id"])).fetchone()
        if ev:
            d = json.loads(ev["data"])
            last = {"event_id": ev["id"], "at": ev["wall_at"], "t_stream": ev["t_stream"], "decision": d["decision"], "confidence": d["confidence"],
                    "summary": d["summary"], "reason": d["reason"], "frames": d["frames"], "latency_s": d.get("latency_s"), "cost_usd": d.get("cost_usd")}
    out = {k: s[k] for k in ("id", "channel", "project_id", "status", "stop_reason", "error", "lang", "max_minutes", "budget_usd",
                             "max_calls", "min_confidence", "spent_usd", "calls", "recorded_s", "started_at", "stopped_at", "created_at", "updated_at")}
    seg = c.execute("SELECT seq, t_start, duration, wall_start FROM live_segments WHERE session_id=? AND duration>0 ORDER BY seq DESC LIMIT 1",
                    (s["id"],)).fetchone()
    out.update(claude=claude, last_analysis=last, agent_alive=s["locked_until"] > db.now(),
               last_segment=dict(seg) if seg else None)
    if full:
        out["moments"] = moments(c, s["user_id"], s["id"])
    return out


def get(c, uid, sid, full=True):
    s = store.get_session(c, uid, sid)
    if not s: raise LiveError("Sessão não encontrada.", 404)
    return session_out(c, s, full)


def list_sessions(c, uid, limit=20):
    return [session_out(c, s) for s in c.execute("SELECT * FROM live_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (uid, limit))]


def moments(c, uid, sid, status=None):
    q = "SELECT m.*, cl.status AS clip_status FROM live_moments m LEFT JOIN clips cl ON cl.id=m.clip_id WHERE m.session_id=? AND m.user_id=?"
    rows = c.execute(q + (" AND m.status=?" if status else "") + " ORDER BY m.peak DESC LIMIT 200", (sid, uid, *([status] if status else [])))
    return [{"id": m["id"], "peak": m["peak"], "w_start": m["w_start"], "w_end": m["w_end"], "score": m["score"],
             "signals": json.loads(m["signals"]), "status": m["status"], "decision": json.loads(m["decision"]) if m["decision"] else None,
             "clip_id": m["clip_id"] or None, "clip_status": m["clip_status"], "source": m["source"], "error": m["error"],
             "created_at": m["created_at"]} for m in rows]


def recent_context(c, uid, sid, seconds=120):
    s = store.get_session(c, uid, sid)
    if not s: raise LiveError("Sessão não encontrada.", 404)
    a = max(0, s["recorded_s"] - min(float(seconds), 900))
    segs = c.execute("SELECT seq, t_start, duration, wall_start, text, db_max FROM live_segments WHERE session_id=? AND t_start+duration>? "
                     "AND duration>0 ORDER BY seq", (sid, a)).fetchall()
    return {"session_id": sid, "recorded_s": s["recorded_s"], "from_t": a,
            "segments": [{"seq": x["seq"], "t_start": x["t_start"], "duration": x["duration"], "wall_start": x["wall_start"],
                          "db_max": x["db_max"], "text": x["text"]} for x in segs]}


def request_clip(c, uid, sid, moment_id=None, start_t=None, end_t=None):
    s = store.get_session(c, uid, sid)
    if not s: raise LiveError("Sessão não encontrada.", 404)
    if s["status"] not in ("running", "reconnecting"): raise LiveError("A sessão precisa estar gravando (o trecho fica no buffer do agente).", 409)
    busy = c.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND type='render' AND status IN ('queued','running')", (uid,)).fetchone()[0]
    pend = c.execute("SELECT COUNT(*) FROM live_moments WHERE session_id=? AND status='clip_requested'", (sid,)).fetchone()[0]
    if busy + pend >= int(os.environ.get("MAX_USER_RENDERS", "8")): raise LiveError("Muitos cortes na fila. Aguarde os atuais terminarem.", 429)
    if moment_id:
        m = c.execute("SELECT * FROM live_moments WHERE id=? AND session_id=? AND user_id=?", (moment_id, sid, uid)).fetchone()
        if not m: raise LiveError("Momento não encontrado.", 404)
        if m["clip_id"]: raise LiveError("Este momento já virou corte.", 409)
        n = c.execute("UPDATE live_moments SET status='clip_requested', source='manual', updated_at=? WHERE id=? AND clip_id='' AND status IN "
                      "('candidate','rejected','skipped','invalid','expired')", (db.now(), moment_id)).rowcount  # compare-and-set
        if not n: raise LiveError("Este momento já está sendo processado.", 409)
        store.event(c, s, "clip_requested", {"moment_id": moment_id, "by": "user"}, m["peak"]); return moment_id
    a, b = num(start_t, "Início"), num(end_t, "Fim")
    oldest = c.execute("SELECT MIN(t_start) FROM live_segments WHERE session_id=? AND deleted=0 AND duration>0", (sid,)).fetchone()[0]
    if b - a < 5 or b - a > 60: raise LiveError("O corte precisa ter entre 5 e 60 segundos.")
    if oldest is None or a < oldest or a > s["recorded_s"] + 60:
        raise LiveError(f"Trecho fora do buffer: disponível de t={oldest or 0:.0f}s até t={s['recorded_s']:.0f}s.")
    mid = db.new_id("mom")
    c.execute("INSERT INTO live_moments(id,session_id,user_id,peak,w_start,w_end,score,signals,status,source,created_at,updated_at) "
              "VALUES(?,?,?,?,?,?,0,?,'clip_requested','manual',?,?)", (mid, sid, uid, round((a + b) / 2, 2), a, b, json.dumps({"manual": True}), db.now(), db.now()))
    store.event(c, s, "clip_requested", {"moment_id": mid, "start_t": a, "end_t": b, "by": "user"}, a)
    return mid


def render_status(c, uid, clip_id):
    x = c.execute("SELECT * FROM clips WHERE id=? AND user_id=?", (clip_id, uid)).fetchone()
    if not x: raise LiveError("Corte não encontrado.", 404)
    j = c.execute("SELECT status, progress, stage, attempts, error FROM jobs WHERE clip_id=? ORDER BY created_at DESC LIMIT 1", (clip_id,)).fetchone()
    cp = json.loads(x["copy"])
    return {"clip_id": clip_id, "status": x["status"], "screen_title": cp.get("screen_title"), "error": x["error"] or None,
            "job": dict(j) if j else None, "preview_url": f"/api/clips/{clip_id}/video" if x["video_path"] else None,
            "download_url": f"/api/clips/{clip_id}/download" if x["status"] == "approved" else None}


def events_since(c, uid, sid, after_id=0, limit=200):
    return [{"id": e["id"], "kind": e["kind"], "t_stream": e["t_stream"], "wall_at": e["wall_at"], "data": json.loads(e["data"])}
            for e in c.execute("SELECT * FROM live_events WHERE session_id=? AND user_id=? AND id>? ORDER BY id LIMIT ?", (sid, uid, after_id, limit))]


def frame_path(c, uid, fid):
    f = c.execute("SELECT * FROM live_frames WHERE id=? AND user_id=?", (fid, uid)).fetchone()
    if not f: raise LiveError("Frame não encontrado.", 404)
    p = (db.DATA / f["path"]).resolve()
    if db.user_dir(uid).resolve() not in p.parents or not p.exists(): raise LiveError("Frame não encontrado.", 404)
    return p, f
