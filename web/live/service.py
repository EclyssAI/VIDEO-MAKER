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


RIGHTS = {"owner": "Sou o titular do canal", "authorized": "Tenho autorização do titular do canal para gerar cortes"}
CAPACITY_TOTAL = int(os.environ.get("LIVE_CAPACITY_TOTAL", "10"))  # sessões ativas no servidor inteiro (medido em docs/CAPACIDADE_E_CUSTOS.md)


def _tx(c):
    """Transação de escrita exclusiva (SQLite): contagem + inserção sem corrida entre requisições simultâneas."""
    c.execute("BEGIN IMMEDIATE")


def _active_count(c, uid=None):
    q = f"SELECT COUNT(*) FROM live_sessions WHERE status IN {store.ACTIVE}" + (" AND user_id=?" if uid else "")
    return c.execute(q, (uid,) if uid else ()).fetchone()[0]


def connect_stream(c, user, channel, rights_basis=None, platform="twitch"):
    """Conecta uma transmissão a um slot do plano. Exige declaração de direitos (titular ou autorizado)."""
    L = limits_for(user); ch = parse_channel(channel)
    if platform != "twitch": raise LiveError("Plataforma ainda não suportada. Hoje: Twitch.")
    if rights_basis not in RIGHTS:
        raise LiveError("Confirme que você é o titular do canal ou tem autorização do titular (rights_basis: owner ou authorized).", 400)
    _tx(c)
    try:
        hit = c.execute("SELECT * FROM live_streams WHERE user_id=? AND platform=? AND channel=?", (user["id"], platform, ch)).fetchone()
        if hit:
            c.execute("COMMIT"); return stream_out(c, hit)
        used = [r[0] for r in c.execute("SELECT slot FROM live_streams WHERE user_id=? ORDER BY slot", (user["id"],))]
        if len(used) >= L["live_slots"]:
            raise LiveError(f"Seu plano {L['label']} permite até {L['live_slots']} transmissão(ões) conectada(s). Remova uma para conectar outra.", 403)
        slot = next(k for k in range(1, L["live_slots"] + 1) if k not in used)
        t = db.now(); sid = db.new_id("str")
        c.execute("INSERT INTO live_streams(id,user_id,platform,channel,slot,rights_basis,rights_attested_at,created_at,updated_at) "
                  "VALUES(?,?,?,?,?,?,?,?,?)", (sid, user["id"], platform, ch, slot, rights_basis, t, t, t))
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK"); raise
    return stream_out(c, c.execute("SELECT * FROM live_streams WHERE id=?", (sid,)).fetchone())


def own_stream(c, uid, stream_id):
    st = c.execute("SELECT * FROM live_streams WHERE id=? AND user_id=?", (stream_id, uid)).fetchone()
    if not st: raise LiveError("Transmissão não encontrada.", 404)
    return st


def remove_stream(c, uid, stream_id):
    st = own_stream(c, uid, stream_id)
    if st["current_session_id"]:
        try: stop(c, uid, st["current_session_id"])
        except LiveError: pass
    c.execute("DELETE FROM live_streams WHERE id=? AND user_id=?", (stream_id, uid))
    return {"removed": stream_id, "channel": st["channel"]}


def start_stream(c, user, stream_id, budget_usd=None, max_minutes=None, lang="auto", min_confidence=0.6):
    """Inicia o monitoramento de uma transmissão conectada. Limites checados no backend, dentro de uma transação:
    sessões simultâneas do plano (live_slots), franquia mensal, capacidade total do servidor."""
    L = limits_for(user); st = own_stream(c, user["id"], stream_id)
    if lang not in ("auto", "pt", "en", "es"): raise LiveError("Idioma inválido.")
    hours_left, _ = plans.live_quota_left(c, user)
    if hours_left <= 0: raise LiveError(f"Sua franquia de {L['live_hours_per_month']} h de monitoramento deste mês acabou.", 402)
    budget = min(num(budget_usd if budget_usd is not None else L["live_budget_usd_max"], "Orçamento"), L["live_budget_usd_max"])
    minutes = min(num(max_minutes if max_minutes is not None else L["live_max_minutes"], "Duração"), L["live_max_minutes"], hours_left * 60)
    if budget < 0 or minutes < 1: raise LiveError("Orçamento ou duração inválidos.")
    conf = min(max(num(min_confidence, "Confiança"), 0), 1)
    _tx(c)
    try:
        if st["slot"] > L["live_slots"]:
            raise LiveError(f"Esta transmissão ocupa o slot {st['slot']}, acima dos {L['live_slots']} do plano {L['label']}.", 403)
        if c.execute(f"SELECT 1 FROM live_sessions WHERE stream_id=? AND status IN {store.ACTIVE}", (stream_id,)).fetchone():
            raise LiveError("Esta transmissão já está sendo monitorada.", 409)
        if _active_count(c, user["id"]) >= L["live_slots"]:
            raise LiveError(f"Limite do plano {L['label']}: {L['live_slots']} transmissão(ões) monitorada(s) ao mesmo tempo.", 403)
        if _active_count(c) >= CAPACITY_TOTAL:
            raise LiveError("Capacidade de monitoramento do servidor esgotada no momento. Tente novamente em alguns minutos.", 503)
        t = db.now(); sid = db.new_id("live"); pid = db.new_id("prj"); ch = st["channel"]
        c.execute("INSERT INTO projects(id,user_id,name,source_name,lang,status,created_at,updated_at) VALUES(?,?,?,?,?,'live',?,?)",
                  (pid, user["id"], f"Live · {ch} · {time.strftime('%d/%m %H:%M', time.gmtime(t - 3 * 3600))}", f"twitch.tv/{ch}", lang, t, t))
        c.execute("INSERT INTO live_sessions(id,user_id,channel,project_id,status,lang,max_minutes,budget_usd,max_calls,min_confidence,"
                  "stream_id,transcribe_mode,created_at,updated_at) VALUES(?,?,?,?,'starting',?,?,?,?,?,?,?,?,?)",
                  (sid, user["id"], ch, pid, lang, minutes, budget, int(L["live_max_calls"]), conf, stream_id,
                   os.environ.get("LIVE_TRANSCRIBE", "events"), t, t))
        c.execute("UPDATE live_streams SET current_session_id=?, updated_at=? WHERE id=?", (sid, t, stream_id))
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK"); raise
    s = store.get_session(c, user["id"], sid)
    store.event(c, s, "created", {"channel": st["channel"], "stream_id": stream_id, "slot": st["slot"], "budget_usd": budget,
                                  "max_minutes": minutes, "max_calls": int(L["live_max_calls"]), "claude": claude_live.status()[0]}, 0)
    return session_out(c, s)


def pause_stream(c, uid, stream_id):
    st = own_stream(c, uid, stream_id)
    if not st["current_session_id"]: raise LiveError("Esta transmissão não está sendo monitorada.", 409)
    return stop(c, uid, st["current_session_id"])


def start(c, user, channel, budget_usd=None, max_minutes=None, lang="auto", min_confidence=0.6, rights_basis=None):
    """Compatível com a API anterior (um canal por chamada): conecta (se preciso) e inicia."""
    st = connect_stream(c, user, channel, rights_basis)
    return start_stream(c, user, st["id"], budget_usd, max_minutes, lang, min_confidence)


STREAM_STATE = {"starting": "starting", "running": "live", "reconnecting": "reconnecting", "stopping": "stopping"}
STOP_STATE = {"user": "paused", "offline": "offline", "error": "error", "duration": "limit", "budget": "limit", "calls": "limit",
              "quota": "limit", "plan": "limit"}


def stream_out(c, st):
    s = c.execute("SELECT * FROM live_sessions WHERE id=? AND user_id=?", (st["current_session_id"], st["user_id"])).fetchone() \
        if st["current_session_id"] else None
    state = "idle"
    if s: state = STREAM_STATE.get(s["status"]) or STOP_STATE.get(s["stop_reason"], "paused")
    out = {"id": st["id"], "platform": st["platform"], "channel": st["channel"], "slot": st["slot"], "url": f"https://www.twitch.tv/{st['channel']}",
           "rights_basis": st["rights_basis"], "rights_attested_at": st["rights_attested_at"], "state": state, "session": None}
    if s:
        n = c.execute("SELECT COUNT(*) AS n, SUM(clip_id!='') AS k FROM live_moments WHERE session_id=?", (s["id"],)).fetchone()
        last = c.execute("SELECT kind, t_stream, wall_at, data FROM live_events WHERE session_id=? AND kind!='segment' ORDER BY id DESC LIMIT 1",
                         (s["id"],)).fetchone()
        now = db.now()
        out["session"] = {"id": s["id"], "status": s["status"], "stop_reason": s["stop_reason"] or None, "error": s["error"] or None,
                          "recorded_s": round(s["recorded_s"], 1), "started_at": s["started_at"] or None, "stopped_at": s["stopped_at"] or None,
                          "monitoring_s": round(((s["stopped_at"] or now) - s["started_at"]) if s["started_at"] else 0, 1),
                          "candidates": n["n"] or 0, "clips": int(n["k"] or 0), "calls": s["calls"], "spent_usd": s["spent_usd"],
                          "agent_alive": s["locked_until"] > now,
                          "preview": {"url": f"/api/live/streams/{st['id']}/preview?v={int(s['preview_wall'])}", "t_stream": s["preview_t"],
                                      "wall_at": s["preview_wall"]} if s["preview_wall"] else None,
                          "last_event": {"kind": last["kind"], "t_stream": last["t_stream"], "wall_at": last["wall_at"]} if last else None}
    return out


def list_streams(c, uid):
    return [stream_out(c, st) for st in c.execute("SELECT * FROM live_streams WHERE user_id=? ORDER BY slot", (uid,))]


def monitor(c, user):
    """Painel do Live Monitor: slots do plano, uso do mês e estado real de cada transmissão."""
    L = plans.limits(plans.effective_plan(user)); u = plans.usage(c, user["id"])
    return {"plan": L["label"] if L else None, "slots": L["live_slots"] if L else 0, "active": _active_count(c, user["id"]),
            "usage": {"live_hours": u["live_hours"], "live_clips": u["live_clips"], "ai_usd": u["ai_usd"]},
            "quota": {"live_hours_per_month": L["live_hours_per_month"], "live_clips_per_month": L["live_clips_per_month"],
                      "live_ai_usd_per_month": L.get("live_ai_usd_per_month", 0)} if L else None,
            "claude": dict(zip(("state", "detail"), claude_live.status())), "streams": list_streams(c, user["id"]),
            # servidor de TESTE tocando arquivos locais como se fossem lives: a interface mostra isso explicitamente
            "test_source": bool(os.environ.get("LIVE_SOURCE_OVERRIDE"))}


def preview(c, uid, stream_id):
    """Último frame REAL gravado da transmissão (extraído do bloco mais recente pelo agente)."""
    st = own_stream(c, uid, stream_id)
    s = c.execute("SELECT * FROM live_sessions WHERE id=? AND user_id=?", (st["current_session_id"], uid)).fetchone() if st["current_session_id"] else None
    if not s or not s["preview_wall"]: raise LiveError("Ainda não há frame gravado desta transmissão.", 404)
    p = store.preview_path(uid, s["id"])
    if not p.exists(): raise LiveError("Preview indisponível (sessão encerrada e buffer apagado).", 404)
    return p, {"stream_id": stream_id, "session_id": s["id"], "channel": st["channel"], "t_stream": s["preview_t"], "wall_at": s["preview_wall"],
               "age_s": round(db.now() - s["preview_wall"], 1), "session_status": s["status"]}


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
    out = {k: s[k] for k in ("id", "stream_id", "channel", "project_id", "status", "stop_reason", "error", "lang", "max_minutes", "budget_usd",
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
    u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(); q = plans.live_quota_left(c, u) if u else None
    if not q: raise LiveError("Sua conta não tem um plano ativo.", 402)
    if q[1] <= 0: raise LiveError("Sua franquia de cortes do Live Monitor deste mês acabou.", 402)
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


def resolve_session(c, uid, session_id=None, stream_id=None):
    """Aceita session_id ou stream_id (usa a sessão atual/última da transmissão)."""
    if session_id:
        if not store.get_session(c, uid, session_id): raise LiveError("Sessão não encontrada.", 404)
        return session_id
    if stream_id:
        st = own_stream(c, uid, stream_id)
        if not st["current_session_id"]: raise LiveError("Esta transmissão ainda não foi monitorada.", 404)
        return st["current_session_id"]
    raise LiveError("Informe session_id ou stream_id.")


def highlight(c, uid, moment_id):
    """Evidências REAIS de um momento: sinais medidos, transcrição da janela, frames enviados ao Claude (com SHA-256),
    decisão validada e o corte gerado. Nada é inferido aqui."""
    m = c.execute("SELECT m.*, s.channel, s.stream_id FROM live_moments m JOIN live_sessions s ON s.id=m.session_id "
                  "WHERE m.id=? AND m.user_id=?", (moment_id, uid)).fetchone()
    if not m: raise LiveError("Momento não encontrado.", 404)
    segs = c.execute("SELECT words, deleted FROM live_segments WHERE session_id=? AND t_start<? AND t_start+duration>? ORDER BY seq",
                     (m["session_id"], m["w_end"], m["w_start"])).fetchall()
    words = [w for x in segs for w in json.loads(x["words"]) if m["w_start"] <= w["s"] <= m["w_end"]]
    frames = [{"id": f["id"], "t_stream": f["t_stream"], "sha256": f["sha256"], "sent_at": f["sent_at"], "url": f"/api/live/frames/{f['id']}"}
              for f in c.execute("SELECT * FROM live_frames WHERE moment_id=? AND user_id=? ORDER BY t_stream", (moment_id, uid))]
    clip = render_status(c, uid, m["clip_id"]) if m["clip_id"] else None
    return {"id": m["id"], "session_id": m["session_id"], "stream_id": m["stream_id"] or None, "channel": m["channel"], "peak": m["peak"],
            "window": [m["w_start"], m["w_end"]], "score": m["score"], "signals": json.loads(m["signals"]), "status": m["status"],
            "source": m["source"], "decision": json.loads(m["decision"]) if m["decision"] else None, "error": m["error"] or None,
            "transcript": " ".join(w["w"] for w in words), "words": len(words),
            "transcript_available": bool(segs) and not any(x["deleted"] for x in segs) or bool(words),
            "frames_sent_to_claude": frames, "clip": clip, "created_at": m["created_at"]}


def approve_clip(c, uid, clip_id):
    x = c.execute("SELECT * FROM clips WHERE id=? AND user_id=?", (clip_id, uid)).fetchone()
    if not x: raise LiveError("Corte não encontrado.", 404)
    if x["status"] == "approved": return render_status(c, uid, clip_id)
    if x["status"] != "ready": raise LiveError("O corte precisa estar pronto (renderizado) para ser aprovado.", 409)
    c.execute("UPDATE clips SET status='approved', updated_at=? WHERE id=? AND user_id=? AND status='ready'", (db.now(), clip_id, uid))
    return render_status(c, uid, clip_id)


def render_jobs(c, uid, status=None, limit=50):
    q = ("SELECT j.id, j.status, j.progress, j.stage, j.attempts, j.error, j.created_at, j.updated_at, j.clip_id, j.project_id, "
         "cl.status AS clip_status, p.name AS project FROM jobs j LEFT JOIN clips cl ON cl.id=j.clip_id LEFT JOIN projects p ON p.id=j.project_id "
         "WHERE j.user_id=? AND j.type='render'" + (" AND j.status=?" if status else "") + " ORDER BY j.created_at DESC LIMIT ?")
    return [dict(r) for r in c.execute(q, (uid, *([status] if status else []), max(1, min(int(limit), 200))))]
