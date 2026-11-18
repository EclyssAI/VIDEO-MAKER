"""ClipeiAki (ex-VIDEO-MAKER) Web — API + interface + MCP. Rodar: uvicorn web.app:app  (o processamento roda em `python -m web.worker`)."""
import asyncio, json, os, re, shutil, logging, unicodedata
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import contextlib
from . import db, auth, plans, billing, copywriter, mcp_server
from .worker import enqueue
from .live.api import router as live_router
from .live import claude_live

log = logging.getLogger("web")
STATIC = db.ROOT / "web/static"
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".ts", ".m4v"}
LANGS = {"auto", "pt", "en", "es"}
MAX_ACTIVE_PROJECTS = 2

db.init()
_mcp_app = mcp_server.http_app()


@contextlib.asynccontextmanager
async def lifespan(_):
    async with mcp_server.mcp.session_manager.run():
        yield

api = FastAPI(title="ClipeiAki", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app = api  # substituído no fim do arquivo pelo roteador ASGI que inclui o /mcp


@app.middleware("http")
async def guard(request: Request, call_next):
    p = request.url.path
    # CSRF: toda escrita na API exige header customizado (navegador não envia cross-site sem preflight; não há CORS)
    if p.startswith("/api/") and request.method not in ("GET", "HEAD") and not p.startswith("/api/webhooks/") \
            and request.headers.get("x-vm") != "1":
        return JSONResponse({"detail": "Requisição recusada."}, status_code=403)
    r = await call_next(request)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin",
                      "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
                      "style-src 'self'; script-src 'self'; connect-src 'self'; frame-src https://player.twitch.tv; "
                      "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
    if p.startswith("/api/"): r.headers["Cache-Control"] = "no-store"
    return r


MAX_USER_RENDERS = int(os.environ.get("MAX_USER_RENDERS", "8"))


def render_backlog(c, uid):
    return c.execute("SELECT COUNT(*) FROM jobs WHERE user_id=? AND type='render' AND status IN ('queued','running')", (uid,)).fetchone()[0]


def one_line(v):
    """Texto que vai para a legenda (.ass): sem quebras de linha nem sequências de controle."""
    return re.sub(r"[\r\n\t\\]+", " ", str(v))


def current_user(c, request: Request, required=True):
    u = auth.user_from_token(c, request.cookies.get(auth.COOKIE))
    if not u and required: raise HTTPException(401, "Faça login para continuar.")
    return u


def me_payload(c, u):
    plan = plans.effective_plan(u); L = plans.limits(plan)
    return {"id": u["id"], "email": u["email"], "name": u["name"], "handle": u["handle"], "plan": plan,
            "plan_label": L["label"] if L else None, "plan_status": u["plan_status"], "plan_until": u["plan_until"],
            "limits": L, "usage": plans.usage(c, u["id"]), "claude_copy": copywriter.enabled(),
            "live_claude": dict(zip(("state", "detail"), claude_live.status())), "public_url": mcp_server.PUBLIC_URL}


async def body(request):
    try: return await request.json()
    except Exception: raise HTTPException(400, "JSON inválido.")


def set_cookie(resp, token):
    resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                    secure=auth.secure_cookies(), path="/")


# ---------- autenticação ----------
@app.post("/api/auth/signup")
async def signup(request: Request):
    b = await body(request); email = str(b.get("email", "")).strip().lower(); pw = b.get("password")
    if not auth.valid_email(email): raise HTTPException(400, "Informe um e-mail válido.")
    if not auth.valid_password(pw): raise HTTPException(400, "A senha precisa ter pelo menos 8 caracteres.")
    invite = os.environ.get("SIGNUP_INVITE_CODE")
    if invite and b.get("invite") != invite: raise HTTPException(403, "Código de convite inválido.")
    key = f"signup:{request.client.host if request.client else ''}"
    if auth.throttled(key, limit=10, window=3600): raise HTTPException(429, "Muitas tentativas. Tente mais tarde.")
    with db.conn() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            auth.record_fail(key); raise HTTPException(409, "Já existe uma conta com este e-mail. Entre com sua senha.")
        uid = db.new_id("usr")
        c.execute("INSERT INTO users(id,email,pw_hash,name,created_at) VALUES(?,?,?,?,?)",
                  (uid, email, await asyncio.to_thread(auth.hash_pw, pw), str(b.get("name", ""))[:80], db.now()))
        billing.apply_pending(c, email)
        token = auth.create_session(c, uid); u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        resp = JSONResponse(me_payload(c, u))
    auth.record_fail(key); set_cookie(resp, token); return resp


@app.post("/api/auth/login")
async def login(request: Request):
    b = await body(request); email = str(b.get("email", "")).strip().lower()
    key = f"login:{request.client.host if request.client else ''}:{email}"
    ekey = f"login-email:{email}"  # limite por conta, independente do IP (IP pode ser forjado atrás de proxy mal configurado)
    if auth.throttled(key) or auth.throttled(ekey, limit=20): raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.")
    with db.conn() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        ok = await asyncio.to_thread(auth.check_pw, str(b.get("password", "")), u["pw_hash"] if u else auth.DUMMY_HASH)
        if not u or not ok:
            auth.record_fail(key); auth.record_fail(ekey); raise HTTPException(401, "E-mail ou senha incorretos.")
        token = auth.create_session(c, u["id"]); resp = JSONResponse(me_payload(c, u))
    set_cookie(resp, token); return resp


@app.post("/api/auth/logout")
async def logout(request: Request):
    with db.conn() as c: auth.destroy_session(c, request.cookies.get(auth.COOKIE))
    r = JSONResponse({"ok": True}); r.delete_cookie(auth.COOKIE, path="/"); return r


@app.get("/api/me")
def me(request: Request):
    with db.conn() as c: return me_payload(c, current_user(c, request))


@app.patch("/api/me")
async def update_me(request: Request):
    b = await body(request)
    with db.conn() as c:
        u = current_user(c, request)
        handle = re.sub(r"[^A-Za-z0-9_.@]", "", str(b.get("handle", u["handle"])))[:30]
        c.execute("UPDATE users SET name=?, handle=? WHERE id=?", (str(b.get("name", u["name"]))[:80], handle, u["id"]))
        return me_payload(c, c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone())


# ---------- projetos ----------
def project_out(c, p, with_clips=False):
    job = c.execute("SELECT status, progress, stage, error FROM jobs WHERE project_id=? AND type='analyze' ORDER BY created_at DESC LIMIT 1",
                    (p["id"],)).fetchone()
    counts = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM clips WHERE project_id=? GROUP BY status", (p["id"],))}
    thumb = c.execute("SELECT id FROM clips WHERE project_id=? AND thumb_path!='' ORDER BY idx LIMIT 1", (p["id"],)).fetchone()
    out = {"id": p["id"], "name": p["name"], "status": p["status"], "error": p["error"], "duration": p["duration"],
           "lang": p["lang"], "source_name": p["source_name"], "created_at": p["created_at"], "updated_at": p["updated_at"],
           "clips": counts, "cover_clip": thumb["id"] if thumb else None,
           "job": dict(job) if job else None}
    if with_clips:
        out["items"] = [clip_out(c, x) for x in c.execute("SELECT * FROM clips WHERE project_id=? ORDER BY idx", (p["id"],))]
    return out


def clip_out(c, x):
    cp = json.loads(x["copy"]); job = c.execute("SELECT status, progress, stage, attempts FROM jobs WHERE clip_id=? ORDER BY created_at DESC LIMIT 1",
                                                (x["id"],)).fetchone()
    return {"id": x["id"], "project_id": x["project_id"], "idx": x["idx"], "start": x["start"], "end": x["end"],
            "duration": round(x["end"] - x["start"], 1), "strength": x["strength"], "status": x["status"], "error": x["error"],
            "copy": cp, "has_video": bool(x["video_path"]), "updated_at": x["updated_at"], "job": dict(job) if job else None}


def own_project(c, uid, pid):
    p = c.execute("SELECT * FROM projects WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    if not p: raise HTTPException(404, "Projeto não encontrado.")
    return p


def own_clip(c, uid, cid):
    x = c.execute("SELECT * FROM clips WHERE id=? AND user_id=?", (cid, uid)).fetchone()
    if not x: raise HTTPException(404, "Corte não encontrado.")
    return x


@app.get("/api/projects")
def list_projects(request: Request):
    with db.conn() as c:
        u = current_user(c, request)
        return [project_out(c, p) for p in c.execute("SELECT * FROM projects WHERE user_id=? AND status!='uploading' ORDER BY created_at DESC LIMIT 200", (u["id"],))]


@app.post("/api/projects")
async def create_project(request: Request):
    b = await body(request)
    name = str(b.get("name") or "").strip()[:80] or "Projeto sem nome"
    fname = str(b.get("filename") or "")[:200]; ext = os.path.splitext(fname)[1].lower(); lang = b.get("lang", "auto")
    if ext not in ALLOWED_EXT: raise HTTPException(400, "Formato não suportado. Envie MP4, MOV, MKV, WEBM ou TS.")
    if lang not in LANGS: raise HTTPException(400, "Idioma inválido.")
    with db.conn() as c:
        u = current_user(c, request)
        ok, msg = plans.check_new_project(c, u, size_bytes=int(b.get("size") or 0))
        if not ok: raise HTTPException(402, msg)
        active = c.execute("SELECT COUNT(*) FROM projects WHERE user_id=? AND status IN ('queued','processing','rendering')", (u["id"],)).fetchone()[0]
        if active >= MAX_ACTIVE_PROJECTS: raise HTTPException(429, f"Aguarde: você já tem {active} projetos em processamento.")
        pid = db.new_id("prj"); t = db.now()
        c.execute("DELETE FROM projects WHERE user_id=? AND status='uploading' AND created_at<?", (u["id"], t - 86400))
        c.execute("INSERT INTO projects(id,user_id,name,source_name,lang,status,created_at,updated_at) VALUES(?,?,?,?,?,'uploading',?,?)",
                  (pid, u["id"], name, fname, lang, t, t))
        (db.user_dir(u["id"]) / "projects" / pid).mkdir(parents=True, exist_ok=True)
        c.execute("UPDATE projects SET source_file=? WHERE id=?", ("source" + ext, pid))
        return {"id": pid}


@app.put("/api/projects/{pid}/source")
async def upload_source(pid: str, request: Request):
    from . import engine  # importa o motor só quando necessário
    with db.conn() as c:
        u = current_user(c, request); p = own_project(c, u["id"], pid)
        if p["status"] != "uploading": raise HTTPException(409, "Este projeto já recebeu o vídeo.")
        L = plans.limits(plans.effective_plan(u))
        if not L: raise HTTPException(402, "Sua conta não tem um plano ativo.")
    limit = L["max_upload_mb"] * 1024 * 1024; dest = db.user_dir(u["id"]) / "projects" / pid / p["source_file"]
    size = 0
    try:
        with open(dest, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit: raise HTTPException(413, f"Arquivo maior que o limite do plano ({L['max_upload_mb']} MB).")
                f.write(chunk)
        if size == 0: raise HTTPException(400, "Arquivo vazio.")
        info = await asyncio.to_thread(engine.probe, dest)
    except HTTPException:
        dest.unlink(missing_ok=True); raise
    except engine.EngineError as e:
        dest.unlink(missing_ok=True)
        with db.conn() as c: c.execute("UPDATE projects SET status='failed', error=?, updated_at=? WHERE id=?", (str(e), db.now(), pid))
        raise HTTPException(400, str(e))
    with db.conn() as c:
        u = current_user(c, request)
        ok, msg = plans.check_new_project(c, u, size_bytes=size, duration_s=info["duration"])
        if not ok:
            dest.unlink(missing_ok=True); c.execute("DELETE FROM projects WHERE id=?", (pid,)); raise HTTPException(402, msg)
        c.execute("BEGIN IMMEDIATE")
        plans.charge(c, u["id"], info["duration"])
        c.execute("UPDATE projects SET status='queued', duration=?, updated_at=? WHERE id=?", (info["duration"], db.now(), pid))
        enqueue(c, u["id"], "analyze", pid)
        c.execute("COMMIT")
        return project_out(c, own_project(c, u["id"], pid))


@app.get("/api/projects/{pid}")
def get_project(pid: str, request: Request):
    with db.conn() as c:
        u = current_user(c, request); return project_out(c, own_project(c, u["id"], pid), with_clips=True)


@app.post("/api/projects/{pid}/retry")
def retry_project(pid: str, request: Request):
    with db.conn() as c:
        u = current_user(c, request); p = own_project(c, u["id"], pid)
        if p["status"] != "failed" or not (db.user_dir(u["id"]) / "projects" / pid / (p["source_file"] or "x")).exists():
            raise HTTPException(409, "Só é possível reprocessar projetos com falha que ainda têm o vídeo.")
        c.execute("UPDATE projects SET status='queued', error='', updated_at=? WHERE id=?", (db.now(), pid))
        enqueue(c, u["id"], "analyze", pid); return project_out(c, own_project(c, u["id"], pid))


@app.delete("/api/projects/{pid}")
def delete_project(pid: str, request: Request):
    with db.conn() as c:
        u = current_user(c, request); own_project(c, u["id"], pid)
        c.execute("UPDATE jobs SET status='canceled' WHERE project_id=? AND status IN ('queued')", (pid,))
        c.execute("DELETE FROM projects WHERE id=? AND user_id=?", (pid, u["id"]))
    shutil.rmtree(db.user_dir(u["id"]) / "projects" / pid, ignore_errors=True)
    return {"ok": True}


# ---------- cortes ----------
@app.patch("/api/clips/{cid}")
async def edit_clip(cid: str, request: Request):
    b = await body(request)
    with db.conn() as c:
        u = current_user(c, request); x = own_clip(c, u["id"], cid); cp = json.loads(x["copy"])
        if x["status"] in ("queued", "rendering"): raise HTTPException(409, "Aguarde a renderização atual terminar.")
        for k, n in (("screen_title", 40), ("title", 100), ("description", 2000)):
            if k in b: cp[k] = (str(b[k]) if k == "description" else one_line(b[k])).strip()[:n]
        if "hashtags" in b:
            cp["hashtags"] = ["#" + re.sub(r"[^\wÀ-ÿ]", "", h.lstrip("#"))[:30] for h in str(b["hashtags"]).split() if h.strip("#")][:8]
        if "captions" in b and isinstance(b["captions"], list):
            caps = cp.get("captions", [])
            for i, t in enumerate(b["captions"][:len(caps)]): caps[i]["t"] = one_line(t)[:80]
            cp["captions"] = [k for k in caps if k["t"].strip()]
        if not cp.get("screen_title"): raise HTTPException(400, "O título na tela não pode ficar vazio.")
        if render_backlog(c, u["id"]) >= MAX_USER_RENDERS: raise HTTPException(429, "Muitos cortes na fila. Aguarde os atuais terminarem.")
        c.execute("UPDATE clips SET copy=?, status='queued', updated_at=? WHERE id=?", (json.dumps(cp, ensure_ascii=False), db.now(), cid))
        c.execute("UPDATE projects SET status='rendering', updated_at=? WHERE id=? AND status='done'", (db.now(), x["project_id"]))
        enqueue(c, u["id"], "render", x["project_id"], cid)
        return clip_out(c, own_clip(c, u["id"], cid))


@app.post("/api/clips/{cid}/{action}")
def clip_action(cid: str, action: str, request: Request):
    if action not in ("approve", "discard", "restore", "retry"): raise HTTPException(404)
    with db.conn() as c:
        u = current_user(c, request); x = own_clip(c, u["id"], cid)
        if action == "retry":
            if x["status"] != "failed": raise HTTPException(409, "Este corte não está com falha.")
            c.execute("UPDATE clips SET status='queued', error='' WHERE id=?", (cid,)); enqueue(c, u["id"], "render", x["project_id"], cid)
        else:
            want = {"approve": ("ready", "approved"), "discard": (None, "discarded"), "restore": ("discarded", None)}[action]
            if action == "approve" and x["status"] != "ready": raise HTTPException(409, "O corte precisa estar pronto para ser aprovado.")
            if action == "discard" and x["status"] in ("queued", "rendering"): raise HTTPException(409, "Aguarde a renderização.")
            if action == "restore" and x["status"] != "discarded": raise HTTPException(409, "O corte não está descartado.")
            new = want[1] or ("ready" if x["video_path"] else "failed")
            c.execute("UPDATE clips SET status=?, updated_at=? WHERE id=?", (new, db.now(), cid))
        return clip_out(c, own_clip(c, u["id"], cid))


def clip_file(request, cid, kind):
    with db.conn() as c:
        u = current_user(c, request); x = own_clip(c, u["id"], cid)
        rel = x["thumb_path"] if kind == "thumb" else x["video_path"]
        if not rel: raise HTTPException(404, "Arquivo ainda não disponível.")
        base = (db.user_dir(u["id"]) / "projects" / x["project_id"]).resolve(); f = (base / rel).resolve()
        if base not in f.parents or not f.exists(): raise HTTPException(404, "Arquivo não encontrado.")
        return x, f


@app.get("/api/clips/{cid}/video")
def clip_video(cid: str, request: Request):
    _, f = clip_file(request, cid, "video"); return FileResponse(f, media_type="video/mp4")


@app.get("/api/clips/{cid}/thumb")
def clip_thumb(cid: str, request: Request):
    _, f = clip_file(request, cid, "thumb"); return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"})


@app.get("/api/clips/{cid}/download")
def clip_download(cid: str, request: Request):
    x, f = clip_file(request, cid, "video")
    if x["status"] != "approved": raise HTTPException(403, "Aprove o corte antes de baixar.")
    t = unicodedata.normalize("NFKD", json.loads(x["copy"]).get("screen_title", "corte")).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40] or "corte"
    return FileResponse(f, media_type="video/mp4", filename=f"{x['idx']:02d}-{slug}.mp4")


@app.get("/api/clips/{cid}/caption.txt")
def clip_caption(cid: str, request: Request):
    with db.conn() as c:
        u = current_user(c, request); x = own_clip(c, u["id"], cid); cp = json.loads(x["copy"])
    txt = f"{cp.get('title', '')}\n\n{cp.get('description', '')}\n\n{' '.join(cp.get('hashtags', []))}\n"
    return Response(txt, media_type="text/plain; charset=utf-8")


@app.get("/api/library")
def library(request: Request):
    with db.conn() as c:
        u = current_user(c, request)
        rows = c.execute("SELECT c.*, p.name AS pname FROM clips c JOIN projects p ON p.id=c.project_id "
                         "WHERE c.user_id=? AND c.status='approved' ORDER BY c.updated_at DESC LIMIT 500", (u["id"],)).fetchall()
        return [{**clip_out(c, x), "project_name": x["pname"]} for x in rows]


# ---------- assinatura ----------
@app.get("/api/billing")
def billing_info(request: Request):
    with db.conn() as c:
        u = current_user(c, request)
        return {"enabled": billing.enabled(), "checkout": billing.checkout_urls(), "me": me_payload(c, u),
                "plans": {k: v for k, v in plans.PLANS.items() if k in ("creator", "studio")}}


@app.post("/api/webhooks/cakto")
async def cakto_webhook(request: Request):
    if not billing.enabled(): return JSONResponse({"detail": "Pagamentos desativados."}, status_code=503)
    raw = await request.body()
    try: b = json.loads(raw)
    except Exception: return JSONResponse({"detail": "JSON inválido."}, status_code=400)
    if not billing.verify(raw, {k.lower(): v for k, v in request.headers.items()}, b):
        log.warning("webhook cakto com assinatura inválida"); return JSONResponse({"detail": "Não autorizado."}, status_code=401)
    with db.conn() as c:
        c.execute("BEGIN IMMEDIATE"); r = billing.handle(c, b); c.execute("COMMIT")
    return r


@app.get("/healthz")
def healthz():
    with db.conn() as c:
        q = c.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
    return {"ok": True, "queue": q, "ffmpeg": bool(shutil.which("ffmpeg"))}


# ---------- interface ----------
app.include_router(live_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/{path:path}")
def spa(path: str):
    if path.startswith("api/"): raise HTTPException(404)
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


MAX_BODY = int(os.environ.get("MAX_JSON_BODY", str(256 * 1024)))
_UPLOAD = re.compile(r"^/api/projects/[^/]+/source$")


class BodyTooLarge(Exception): pass


class _Router:
    """ASGI: /mcp e o metadata OAuth do recurso vão para o servidor MCP oficial; o resto para a API/interface.
    Também limita o corpo das requisições (exceto o upload de vídeo, que tem limite próprio por plano)."""
    def __init__(self, web, mcp): self.web, self.mcp = web, mcp

    async def __call__(self, scope, receive, send):
        p = scope.get("path", "") if scope["type"] in ("http", "websocket") else ""
        if p == "/mcp" or p.startswith("/mcp/") or p.startswith("/.well-known/oauth-protected-resource"):
            return await self.mcp(scope, receive, send)
        if scope["type"] != "http" or _UPLOAD.match(p) or scope.get("method") in ("GET", "HEAD"):
            return await self.web(scope, receive, send)
        cl = dict(scope.get("headers") or []).get(b"content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY: return await self._413(send)
        seen = 0
        async def capped():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > MAX_BODY: raise BodyTooLarge()
            return msg
        try:
            return await self.web(scope, capped, send)
        except BodyTooLarge:
            return await self._413(send)

    async def _413(self, send):
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": '{"detail":"Requisição grande demais."}'.encode()})


app = _Router(api, _mcp_app)
