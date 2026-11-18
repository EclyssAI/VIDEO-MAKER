"""Worker de processamento (processo separado do servidor web).
Fila persistente na tabela jobs: claim atômico com lease; se o processo morrer, o lease expira e o job volta à fila
(até max_attempts). Uso: python -m web.worker"""
import json, os, shutil, signal, socket, threading, time, traceback, logging
from . import db, plans, engine, copywriter

LEASE_S = int(os.environ.get("VM_LEASE_S", "180"))
WORKER = f"{socket.gethostname()}:{os.getpid()}"
log = logging.getLogger("worker")
_stop = False


def enqueue(c, uid, type_, project_id=None, clip_id=None):
    jid = db.new_id("job"); t = db.now()
    c.execute("INSERT INTO jobs(id,user_id,project_id,clip_id,type,status,created_at,updated_at) VALUES(?,?,?,?,?,'queued',?,?)",
              (jid, uid, project_id, clip_id, type_, t, t))
    return jid


def claim(c):
    t = db.now()
    return c.execute("""UPDATE jobs SET status='running', attempts=attempts+1, locked_until=?, worker=?, updated_at=?, stage='Iniciando'
        WHERE id=(SELECT id FROM jobs WHERE (status='queued') OR (status='running' AND locked_until<?)
                  ORDER BY CASE type WHEN 'analyze' THEN 0 ELSE 1 END, created_at LIMIT 1)
        RETURNING *""", (t + LEASE_S, WORKER, t, t)).fetchone()


def progress(c, job, pct, stage):
    c.execute("UPDATE jobs SET progress=?, stage=?, locked_until=?, updated_at=? WHERE id=?",
              (round(pct, 1), stage, db.now() + LEASE_S, db.now(), job["id"]))


def project_paths(uid, pid):
    base = db.user_dir(uid) / "projects" / pid
    return base, base / "clips"


def run_analyze(c, job):
    p = c.execute("SELECT * FROM projects WHERE id=? AND user_id=?", (job["project_id"], job["user_id"])).fetchone()
    user = c.execute("SELECT * FROM users WHERE id=?", (job["user_id"],)).fetchone()
    if not p or not user: raise engine.EngineError("Projeto não encontrado.")
    L = plans.limits(plans.effective_plan(user)) or plans.PLANS["beta"]
    c.execute("UPDATE projects SET status='processing', error='', updated_at=? WHERE id=?", (db.now(), p["id"]))
    # retomada idempotente: apaga cortes de uma tentativa anterior
    base, clips_dir = project_paths(p["user_id"], p["id"])
    c.execute("DELETE FROM clips WHERE project_id=?", (p["id"],)); shutil.rmtree(clips_dir, ignore_errors=True)
    clips, lang = engine.analyze(base / p["source_file"], p["lang"], L["clips_per_project"],
                                 lambda pct, s: progress(c, job, pct * 0.8, s))
    progress(c, job, 70, "Escrevendo títulos e legendas")
    copies = copywriter.make_copy(clips, lang, p["name"])
    t = db.now()
    for k, cl in enumerate(clips):
        cid = db.new_id("clip"); cl["src"] = p["source_file"]  # caminho relativo ao projeto (não vaza no cliente)
        c.execute("INSERT INTO clips(id,user_id,project_id,idx,start,end,peak,strength,data,copy,status,created_at,updated_at) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?)", (cid, p["user_id"], p["id"], k + 1, cl["start"], cl["end"],
                  cl["peak"], cl["strength"], json.dumps(cl), json.dumps(copies[cl["id"]], ensure_ascii=False), t, t))
        enqueue(c, p["user_id"], "render", p["id"], cid)
    status = "rendering" if clips else "done"
    c.execute("UPDATE projects SET status=?, lang=?, updated_at=? WHERE id=?", (status, lang, db.now(), p["id"]))


def run_render(c, job):
    cl = c.execute("SELECT * FROM clips WHERE id=? AND user_id=?", (job["clip_id"], job["user_id"])).fetchone()
    user = c.execute("SELECT * FROM users WHERE id=?", (job["user_id"],)).fetchone()
    if not cl or not user: raise engine.EngineError("Corte não encontrado.")
    base, clips_dir = project_paths(cl["user_id"], cl["project_id"])
    c.execute("UPDATE clips SET status='rendering', error='', updated_at=? WHERE id=?", (db.now(), cl["id"]))
    progress(c, job, 10, "Renderizando corte")
    data = json.loads(cl["data"]); cp = json.loads(cl["copy"]); data["src"] = str(base / data["src"])
    data["streamer"] = user["handle"] or user["name"] or "criador"
    premium = bool((plans.limits(plans.effective_plan(user)) or {}).get("premium_assets"))
    assets = engine.brand_pack(db.user_dir(user["id"]) / "brand" / (user["handle"] or "_").strip("@")[:40].replace("/", "_"), user["handle"])
    tmp = clips_dir / f"{cl['id']}.tmp"; shutil.rmtree(tmp, ignore_errors=True)
    out = engine.render(data, {**cp, "title": cp.get("title") or cp["screen_title"], "description": cp.get("description", ""),
                               "hashtags": cp.get("hashtags", [])}, tmp, cl["idx"], assets, premium)
    final = clips_dir / cl["id"]; shutil.rmtree(final, ignore_errors=True); out.rename(final); shutil.rmtree(tmp, ignore_errors=True)
    rel = final.relative_to(base)
    c.execute("UPDATE clips SET status='ready', video_path=?, thumb_path=?, updated_at=? WHERE id=?",
              (str(rel / "video.mp4"), str(rel / "thumb.jpg"), db.now(), cl["id"]))
    finish_project_if_done(c, cl["project_id"])


def finish_project_if_done(c, pid):
    left = c.execute("SELECT COUNT(*) FROM jobs WHERE project_id=? AND status IN ('queued','running')", (pid,)).fetchone()[0]
    if left <= 1:  # o job atual ainda está 'running'
        c.execute("UPDATE projects SET status='done', updated_at=? WHERE id=? AND status IN ('rendering','processing')", (db.now(), pid))


def fail(c, job, err, msg):
    final = job["attempts"] >= job["max_attempts"] or isinstance(err, engine.EngineError)
    c.execute("UPDATE jobs SET status=?, error=?, locked_until=0, updated_at=? WHERE id=?",
              ("failed" if final else "queued", msg, db.now(), job["id"]))
    if final:
        if job["type"] == "analyze":
            c.execute("UPDATE projects SET status='failed', error=?, updated_at=? WHERE id=?", (msg, db.now(), job["project_id"]))
        else:
            c.execute("UPDATE clips SET status='failed', error=?, updated_at=? WHERE id=?", (msg, db.now(), job["clip_id"]))
            finish_project_if_done(c, job["project_id"])


def _heartbeat(jid, done):
    """Renova o lease enquanto o job roda (renders longos), para outro worker não pegar o mesmo job."""
    with db.conn() as hc:
        while not done.wait(min(30, LEASE_S / 3)):
            hc.execute("UPDATE jobs SET locked_until=? WHERE id=? AND status='running'", (db.now() + LEASE_S, jid))


def run_once(c):
    job = claim(c)
    if not job: return False
    log.info("job %s %s tentativa %s", job["id"], job["type"], job["attempts"])
    done = threading.Event(); threading.Thread(target=_heartbeat, args=(job["id"], done), daemon=True).start()
    try:
        (run_analyze if job["type"] == "analyze" else run_render)(c, job)
        c.execute("UPDATE jobs SET status='done', progress=100, stage='Concluído', locked_until=0, updated_at=? WHERE id=?",
                  (db.now(), job["id"]))
    except engine.EngineError as e:
        fail(c, job, e, str(e))
    except Exception as e:
        log.error("job %s falhou: %s", job["id"], traceback.format_exc()[-1500:])
        fail(c, job, e, "Erro interno no processamento. Tentaremos novamente." if job["attempts"] < job["max_attempts"]
             else "Erro interno no processamento.")
    finally:
        done.set()
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init()
    def stop(*_):
        global _stop; _stop = True
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    log.info("worker %s pronto (dados em %s)", WORKER, db.DATA)
    with db.conn() as c:
        while not _stop:
            if not run_once(c): time.sleep(1.5)


if __name__ == "__main__": main()
