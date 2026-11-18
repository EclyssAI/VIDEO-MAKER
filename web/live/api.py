"""Rotas do Claude Live Monitor: REST + SSE. Autenticação pela sessão do navegador (cookie), isolamento por user_id."""
import asyncio, hashlib, json, os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from .. import db, auth, tokens
from . import service, store

router = APIRouter()
SSE_MAX_S = float(os.environ.get("LIVE_SSE_MAX_S", "280"))  # cabe numa função da Vercel; o EventSource reconecta sozinho
SSE_PER_USER, SSE_TOTAL = int(os.environ.get("LIVE_SSE_PER_USER", "4")), int(os.environ.get("LIVE_SSE_TOTAL", "200"))
_streams = {}


def user_of(c, request):
    u = auth.user_from_token(c, request.cookies.get(auth.COOKIE))
    if not u: raise HTTPException(401, "Faça login para continuar.")
    return u


def call(fn, *a, **kw):
    try: return fn(*a, **kw)
    except service.LiveError as e: raise HTTPException(e.code, str(e))


async def body(request):
    try: return await request.json()
    except Exception: raise HTTPException(400, "JSON inválido.")


@router.get("/api/live/channel")
def channel(q: str, request: Request):
    with db.conn() as c: u = user_of(c, request)
    return call(service.channel_status, q, u["id"])


@router.get("/api/live/sessions")
def sessions(request: Request):
    with db.conn() as c: return service.list_sessions(c, user_of(c, request)["id"])


@router.post("/api/live/sessions")
async def start(request: Request):
    b = await body(request)
    with db.conn() as c:
        u = user_of(c, request)
        return call(service.start, c, u, b.get("channel"), b.get("budget_usd"), b.get("max_minutes"), b.get("lang", "auto"))


@router.get("/api/live/sessions/{sid}")
def get(sid: str, request: Request):
    with db.conn() as c: return call(service.get, c, user_of(c, request)["id"], sid)


@router.post("/api/live/sessions/{sid}/stop")
def stop(sid: str, request: Request):
    with db.conn() as c: return call(service.stop, c, user_of(c, request)["id"], sid)


@router.get("/api/live/sessions/{sid}/context")
def context(sid: str, request: Request, seconds: float = 120):
    with db.conn() as c: return call(service.recent_context, c, user_of(c, request)["id"], sid, seconds)


@router.post("/api/live/sessions/{sid}/clips")
async def clip(sid: str, request: Request):
    b = await body(request)
    with db.conn() as c:
        mid = call(service.request_clip, c, user_of(c, request)["id"], sid, b.get("moment_id"), b.get("start_t"), b.get("end_t"))
        return {"moment_id": mid, "status": "clip_requested"}


@router.get("/api/live/frames/{fid}")
def frame(fid: str, request: Request):
    with db.conn() as c:
        p, f = call(service.frame_path, c, user_of(c, request)["id"], fid)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600", "X-Frame-SHA256": f["sha256"],
                                                             "X-Frame-T-Stream": str(f["t_stream"])})


@router.get("/api/live/sessions/{sid}/events")
async def events(sid: str, request: Request, after: int = 0):
    """SSE: eventos reais da tabela live_events (id crescente) + 'snapshot' do estado quando muda."""
    with db.conn() as c:
        u = user_of(c, request); call(service.get, c, u["id"], sid, False)
    uid = u["id"]
    try: last = max(0, int(request.headers.get("last-event-id") or after or 0))
    except ValueError: last = 0
    if _streams.get(uid, 0) >= SSE_PER_USER or sum(_streams.values()) >= SSE_TOTAL:
        raise HTTPException(429, "Muitas conexões abertas com o monitor.")
    _streams[uid] = _streams.get(uid, 0) + 1

    async def gen():
        nonlocal last
        try:
            async for chunk in stream():
                yield chunk
        finally:
            _streams[uid] -= 1
            if _streams[uid] <= 0: _streams.pop(uid, None)

    async def stream():
        nonlocal last
        yield "retry: 2000\n\n"; t0 = asyncio.get_event_loop().time(); prev = None
        while asyncio.get_event_loop().time() - t0 < SSE_MAX_S:
            if await request.is_disconnected(): break
            def read():
                with db.conn() as c:
                    return service.events_since(c, uid, sid, last), service.get(c, uid, sid, True)
            evs, snap = await asyncio.to_thread(read)
            for e in evs:
                last = e["id"]; yield f"id: {e['id']}\nevent: live\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
            h = hashlib.sha1(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()
            if h != prev:
                prev = h; yield f"event: snapshot\ndata: {json.dumps(snap, ensure_ascii=False, default=str)}\n\n"
            if snap["status"] == "stopped" and not evs: break
            yield ": ping\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---------- tokens de API (MCP) ----------
@router.get("/api/tokens")
def list_tokens(request: Request):
    with db.conn() as c: return {"tokens": tokens.list_(c, user_of(c, request)["id"]), "scopes": tokens.SCOPES}


@router.post("/api/tokens")
async def create_token(request: Request):
    b = await body(request)
    with db.conn() as c:
        try: tid, tok, scopes = tokens.create(c, user_of(c, request)["id"], str(b.get("name", "")), b.get("scopes") or [])
        except ValueError as e: raise HTTPException(400, str(e))
    return {"id": tid, "token": tok, "scopes": scopes}


@router.delete("/api/tokens/{tid}")
def revoke_token(tid: str, request: Request):
    with db.conn() as c:
        if not tokens.revoke(c, user_of(c, request)["id"], tid): raise HTTPException(404, "Token não encontrado.")
    return {"ok": True}
