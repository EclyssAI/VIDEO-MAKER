"""ClipeiAki Live Agent — processo contínuo (não roda em função HTTP). Uso: python -m web.live.agent

Para cada sessão (um canal Twitch):
  gravação contínua (streamlink | ffmpeg segment, 10 s) → por segmento: loudness (detect.loudness do João),
  variação de imagem (ffmpeg, 2 fps em 64x36), transcrição (mesmo Whisper do motor) → candidatos por áudio/imagem/
  palavras → thread de análise envia N frames + transcrição à Claude API (claude_live) → decisão JSON validada →
  corte: concatena os segmentos do buffer e enfileira o render no worker existente (render_live.render do João).
A gravação continua enquanto a análise e o render acontecem (threads/processos separados).
Recuperação: lease + heartbeat por sessão; outro agente retoma a sessão, mata o gravador órfão e processa o que ficou."""
import json, logging, os, pathlib, re, shlex, shutil, signal, socket, subprocess, threading, time
from collections import deque
import numpy as np
from .. import db, plans, engine, copywriter
from ..worker import enqueue
from . import store, claude_live

log = logging.getLogger("live")
AGENT = f"{socket.gethostname()}:{os.getpid()}"
E = os.environ.get
LEASE_S = int(E("LIVE_LEASE_S", "45"))
SEG_S = int(E("LIVE_SEGMENT_S", "10"))
BUFFER_S = int(E("LIVE_BUFFER_S", "600"))
PRE_S, POST_S = float(E("LIVE_PRE_S", "15")), float(E("LIVE_POST_S", "8"))
COOLDOWN_S = float(E("LIVE_COOLDOWN_S", "30"))
MIN_CALL_INTERVAL = float(E("LIVE_MIN_CALL_INTERVAL_S", "15"))
AUDIO_DB = float(E("LIVE_AUDIO_DB", "9"))
OFFLINE_S = float(E("LIVE_OFFLINE_S", "180"))
MAX_SESSIONS = int(E("LIVE_MAX_SESSIONS", "2"))
MAX_QUEUE = 3
QUALITY = "720p60,720p,480p,best"
KEYWORDS = [k.strip() for k in E("LIVE_KEYWORDS", "oh my god,what the,no way,holy,let's go,lets go,wtf,bro what,"
            "caralho,nossa,meu deus,mano do céu,kkkk,não acredito,que isso,socorro").split(",") if k.strip()]
LIVE_WHISPER = E("LIVE_WHISPER_MODEL", "base")  # mais leve que o "small" dos cortes: a live precisa acompanhar o tempo real
WHISPER_WORKERS = int(E("LIVE_WHISPER_WORKERS", "2"))  # instâncias do modelo em paralelo (cada uma ~150 MB com int8)
_whisper_lock = threading.Lock(); _whisper_free = []; _whisper_made = 0
_whisper_slots = threading.BoundedSemaphore(WHISPER_WORKERS)
EVENT_TRANSCRIBE_DB = float(E("LIVE_EVENT_TRANSCRIBE_DB", str(AUDIO_DB - 3)))  # modo "events": só blocos com pico ≥ este excesso


def transcribe(path, dur, lang):
    """Mesmo pipeline do motor (faster-whisper, VAD, timestamps por palavra), com modelo próprio para a live.
    Até WHISPER_WORKERS transcrições simultâneas (uma instância de modelo por vaga) para várias transmissões no mesmo agente."""
    global _whisper_made
    from faster_whisper import WhisperModel
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True, timeout=60).stdout
    with _whisper_slots:
        with _whisper_lock:
            if _whisper_free: m = _whisper_free.pop()
            else:
                _whisper_made += 1
                m = WhisperModel(LIVE_WHISPER, compute_type="int8", cpu_threads=int(E("LIVE_WHISPER_THREADS", "2")))
        try:
            # beam 1 + sem condicionar no texto anterior + bloqueio de n-gramas repetidos: ~6x menos CPU que o padrão no mesmo
            # bloco (medido: 15,6 s → 2,4 s de CPU por 10 s de áudio) e sem as alucinações repetitivas do "ha ha ha…"
            segs, info = m.transcribe(np.frombuffer(raw, np.float32), language=lang, word_timestamps=True, vad_filter=True,
                                      beam_size=1, condition_on_previous_text=False, no_repeat_ngram_size=3)
            return [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for g in segs for w in (g.words or [])], info.language
        finally:
            with _whisper_lock: _whisper_free.append(m)
_stop = False


def ffprobe_duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, timeout=30)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0


VISUAL_FULL_MAX = int(E("LIVE_VISUAL_FULL_MAX", "3"))  # acima disto (sessões no mesmo agente), a imagem é medida só nos quadros-chave
ACTIVE_RUNNERS = [0]


def visual_change(p, fps=2, preview=None, keyframes=False):
    """Diferença média entre frames consecutivos (64x36, cinza) — 1 valor a cada 1/fps s.
    keyframes=True decodifica só os quadros-chave (~1 a cada 2 s na Twitch): ~8x menos CPU, resolução temporal menor.
    Com preview=<arquivo>, a MESMA decodificação grava o último frame amostrado (480 px) como preview real da transmissão."""
    args = ["ffmpeg", "-v", "error"] + (["-skip_frame", "nokey"] if keyframes else []) + ["-i", str(p)]
    pick = "" if keyframes else f"fps={fps},"
    sync = ["-fps_mode", "passthrough"] if keyframes else []
    if preview:
        args += ["-filter_complex", f"[0:v]{pick}split=2[a][b];[a]scale=64:36,format=gray[g];[b]scale=480:-2[p]",
                 "-map", "[g]", *sync, "-f", "rawvideo", "pipe:1", "-map", "[p]", *sync, "-q:v", "6", "-update", "1", "-f", "image2", str(preview)]
    else:
        args += ["-vf", f"{pick}scale=64:36,format=gray", *sync, "-f", "rawvideo", "-"]
    raw = subprocess.run(args, capture_output=True, timeout=60).stdout
    fr = np.frombuffer(raw, np.uint8)[: len(raw) // 2304 * 2304].reshape(-1, 2304).astype(np.float32)
    if len(fr) < 2: return np.zeros(max(1, len(fr)))
    return np.concatenate([[0.0], np.abs(np.diff(fr, axis=0)).mean(1)])


def extract_frame(seg_path, offset, width=512):
    # seek na SAÍDA: segmentos .ts começam em PTS≈1,4 s e o seek de entrada falha no último GOP; o segmento é curto (10 s)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(seg_path), "-ss", f"{max(0, offset):.2f}", "-frames:v", "1",
                        "-vf", f"scale={width}:-2", "-q:v", "5", "-f", "image2", "-c:v", "mjpeg", "-"], capture_output=True, timeout=30)
    return r.stdout if r.returncode == 0 and r.stdout else None


def recorder_cmd(channel, out_dir):
    q = shlex.quote; pattern = q(str(out_dir / "seg_%06d.ts"))
    seg = f"-c copy -f segment -segment_time {int(SEG_S)} -reset_timestamps 1 {pattern}"
    src = E("LIVE_SOURCE_OVERRIDE")  # SOMENTE testes simulados: arquivo local tocado em tempo real como se fosse live
    if src and pathlib.Path(src).is_dir():  # pasta de fixtures: <canal>.mp4 se existir, senão um arquivo escolhido pelo nome do canal
        files = sorted(f for f in pathlib.Path(src).iterdir() if f.suffix.lower() in (".mp4", ".mov", ".mkv", ".ts"))
        named = [f for f in files if f.stem == channel]
        src = str(named[0] if named else files[sum(map(ord, channel or "x")) % len(files)])
    if src:
        return f"exec ffmpeg -hide_banner -loglevel error -re -stream_loop -1 -i {q(src)} -map 0:v:0 -map 0:a:0 {seg}"
    if not re.fullmatch(r"[A-Za-z0-9_]{3,25}", channel or ""):  # verificação explícita (não some com python -O)
        raise ValueError("canal inválido")
    return (f"streamlink --twitch-disable-ads --stdout {q('https://www.twitch.tv/' + channel)} {q(QUALITY)} 2>/dev/null | "
            f"ffmpeg -hide_banner -loglevel error -i pipe:0 -map 0:v:0 -map 0:a:0 {seg}")


def is_our_recorder(pgid):
    """Só mata um grupo de processos se ele for mesmo um gravador do agente (evita matar PID reaproveitado)."""
    try: cmd = pathlib.Path(f"/proc/{pgid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
    except OSError: return False
    return "seg_%06d.ts" in cmd


def kill_group(pgid):
    if not pgid: return
    try: os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError): return
    for _ in range(20):
        try: os.killpg(pgid, 0); time.sleep(0.25)
        except ProcessLookupError: return
    try: os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError: pass




def ensure_words(c, sid, sdir, lang, a, b):
    """Transcrição sob demanda: blocos da janela [a, b] ainda não transcritos (modo "events") são transcritos agora,
    com o mesmo modelo, e gravados no banco. Idempotente (UPDATE ... WHERE transcribed=0)."""
    rows = c.execute("SELECT seq, path, t_start, duration FROM live_segments WHERE session_id=? AND transcribed=0 AND deleted=0 "
                     "AND duration>0 AND t_start<? AND t_start+duration>? ORDER BY seq", (sid, b, a)).fetchall()
    for x in rows:
        f = sdir / x["path"]
        if not f.exists(): continue
        raw, _ = transcribe(f, x["duration"], None if lang == "auto" else lang)
        words = [{"w": w["w"], "s": round(x["t_start"] + w["s"], 2), "e": round(x["t_start"] + w["e"], 2)} for w in raw]
        c.execute("UPDATE live_segments SET words=?, text=?, transcribed=1 WHERE session_id=? AND seq=? AND transcribed=0",
                  (json.dumps(words), " ".join(w["w"] for w in words), sid, x["seq"]))
    return len(rows)


STALE_ANALYSIS_S = float(E("LIVE_CLAUDE_TIMEOUT", "90")) * 2 + 30  # chamada + 1 retentativa do SDK + folga


class LostLease(Exception):
    """Outro agente assumiu a sessão: este para sem tocar no estado."""


class Runner(threading.Thread):
    def __init__(self, sid):
        super().__init__(daemon=True, name=f"live-{sid}"); self.sid = sid; self.proc = None; self.run_dir = None
        self.audio_hist = deque(maxlen=int(300 / 0.5)); self.vis_hist = deque(maxlen=int(300 / 0.5))
        self.last_peak = -1e9; self.layout = None; self.down_since = None; self.analyzer = None; self.done = False
        self.last_try = 0; self.proc_started = 0; self._qcheck = 0; self.vis_step = 0.5

    # ------------------------------------------------------------------ ciclo
    def run(self):
        try:
            with db.conn() as c:
                self.c = c; s = self.session()
                self.dir = store.session_dir(s["user_id"], s["id"]); (self.dir / "segments").mkdir(parents=True, exist_ok=True)
                (self.dir / "frames").mkdir(exist_ok=True)
                resumed = c.execute("SELECT COUNT(*) FROM live_segments WHERE session_id=?", (self.sid,)).fetchone()[0] > 0
                if s["recorder_host"] == socket.gethostname() and s["recorder_pgid"] and is_our_recorder(s["recorder_pgid"]):
                    kill_group(s["recorder_pgid"])  # gravador órfão de um agente que caiu nesta mesma máquina
                store.event(c, s, "resumed" if resumed else "started", {"agent": AGENT, "claude": claude_live.status()[0]}, s["recorded_s"])
                c.execute("UPDATE live_sessions SET status='running', started_at=?, updated_at=? WHERE id=? AND status='starting'",
                          (db.now(), db.now(), self.sid))
                self.analyzer = Analyzer(self.sid); self.analyzer.start()
                while not _stop:
                    s = self.heartbeat()
                    if s["status"] == "stopping": self.finalize(s["stop_reason"] or "user"); break
                    reason = self.limit_reached(s)
                    if reason: self.request_stop(s, reason); continue
                    self.ensure_recorder(s)
                    self.process_segments()
                    self.handle_moments(self.session())
                    self.retention(self.session())
                    c.execute("UPDATE live_moments SET status='ready', updated_at=? WHERE session_id=? AND status='analyzing' AND updated_at<?",
                              (db.now(), self.sid, db.now() - STALE_ANALYSIS_S))  # análise órfã (agente anterior caiu no meio)
                    time.sleep(1)
        except LostLease:
            log.warning("sessão %s assumida por outro agente; encerrando este runner", self.sid)
        except Exception:
            log.exception("sessão %s falhou", self.sid)
            self.fail_safe()
        finally:
            if self.analyzer: self.analyzer.stop = True
            if self.proc: kill_group(self.proc.pid)
            self.done = True

    def session(self):
        return self.c.execute("SELECT * FROM live_sessions WHERE id=?", (self.sid,)).fetchone()

    def heartbeat(self):
        """Renova o lease só se a sessão ainda é deste agente."""
        n = self.c.execute("UPDATE live_sessions SET locked_until=? WHERE id=? AND worker=?", (db.now() + LEASE_S, self.sid, AGENT)).rowcount
        if not n: raise LostLease()
        return self.session()

    def fail_safe(self):
        """Erro inesperado: encerra a sessão de forma definitiva (não volta para a fila e não trava o usuário)."""
        try:
            with db.conn() as c:
                s = c.execute("SELECT * FROM live_sessions WHERE id=?", (self.sid,)).fetchone()
                if s and s["status"] in store.ACTIVE and s["worker"] == AGENT:
                    store.update_session(c, self.sid, status="stopped", stop_reason="error", error="Erro interno no agente.",
                                         stopped_at=db.now(), locked_until=0, recorder_pgid=0)
                    c.execute("UPDATE live_moments SET status='expired', updated_at=? WHERE session_id=? AND status IN "
                              "('waiting','ready','analyzing','clip_pending','clip_requested')", (db.now(), self.sid))
                    c.execute("UPDATE projects SET status='done', updated_at=? WHERE id=? AND status='live'", (db.now(), s["project_id"]))
                    store.event(c, s, "stopped", {"reason": "error"}, s["recorded_s"])
            shutil.rmtree(self.dir / "segments", ignore_errors=True)
            for f in self.dir.glob("preview*.jpg"): f.unlink(missing_ok=True)
        except Exception:
            log.exception("fail_safe falhou (sessão %s)", self.sid)

    def limit_reached(self, s):
        if db.now() - self._qcheck >= 10:  # franquia mensal / plano ativo (o uso é somado a cada bloco gravado)
            self._qcheck = db.now(); u = self.c.execute("SELECT * FROM users WHERE id=?", (s["user_id"],)).fetchone()
            q = plans.live_quota_left(self.c, u) if u else None
            if q is None: return "plan"
            if q[0] <= 0: return "quota"
            L = plans.limits(plans.effective_plan(u)); slot = self.c.execute("SELECT slot FROM live_streams WHERE id=?", (s["stream_id"],)).fetchone()
            if L and slot and slot[0] > L["live_slots"]: return "plan"  # plano rebaixado: transmissões acima do novo limite param
        if s["recorded_s"] >= s["max_minutes"] * 60: return "duration"
        if s["budget_usd"] > 0 and s["spent_usd"] >= s["budget_usd"]: return "budget"  # orçamento 0 = sessão sem IA (não para)
        if s["calls"] >= s["max_calls"]: return "calls"
        if s["started_at"] and db.now() - s["started_at"] > s["max_minutes"] * 60 + OFFLINE_S + 120: return "duration"
        return None

    def request_stop(self, s, reason):
        n = self.c.execute("UPDATE live_sessions SET status='stopping', stop_reason=?, updated_at=? WHERE id=? AND status IN "
                           "('starting','running','reconnecting')", (reason, db.now(), self.sid)).rowcount
        if n: store.event(self.c, s, "limit", {"reason": reason, "spent_usd": s["spent_usd"], "calls": s["calls"],
                                               "recorded_s": s["recorded_s"]}, s["recorded_s"])

    # ------------------------------------------------------------------ gravação
    def ensure_recorder(self, s):
        if self.proc and self.proc.poll() is None:
            # gravador vivo mas parado (sem arquivo novo há muito tempo): reinicia
            newest = max((f.stat().st_mtime for f in self.run_dir.glob("seg_*.ts")), default=self.proc_started)
            if db.now() - max(newest, self.proc_started) > max(60, 5 * SEG_S):
                log.warning("gravador sem dados há %.0fs; reiniciando", db.now() - newest); kill_group(self.proc.pid); self.proc.wait(10)
            else:
                return
        if self.proc is not None:  # caiu
            if self.down_since is None:
                self.down_since = db.now()
                if self.c.execute("UPDATE live_sessions SET status='reconnecting', updated_at=? WHERE id=? AND status='running'",
                                  (db.now(), self.sid)).rowcount:
                    store.event(self.c, s, "disconnected", {"exit_code": self.proc.returncode}, s["recorded_s"])
            elif db.now() - self.down_since > OFFLINE_S:
                self.request_stop(s, "offline"); return
            if db.now() - self.last_try < 10: return
        self.last_try = db.now()
        runs = sorted((self.dir / "segments").glob("r*"))
        self.run_dir = self.dir / "segments" / f"r{len(runs):03d}"; self.run_dir.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(["bash", "-c", recorder_cmd(s["channel"], self.run_dir)], start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proc_started = db.now()
        store.update_session(self.c, self.sid, recorder_pgid=self.proc.pid, recorder_host=socket.gethostname())
        log.info("gravador %s iniciado (pid %s) em %s", s["channel"], self.proc.pid, self.run_dir.name)

    def pending_files(self):
        done = {r["path"] for r in self.c.execute("SELECT path FROM live_segments WHERE session_id=?", (self.sid,))}
        out = []
        for rd in sorted((self.dir / "segments").glob("r*")):
            files = sorted(rd.glob("seg_*.ts")); active = (rd == self.run_dir and self.proc and self.proc.poll() is None)
            for k, f in enumerate(files):
                rel = str(f.relative_to(self.dir))
                if rel in done: continue
                if active and k == len(files) - 1: break  # ainda sendo escrito
                out.append(f)
        return out

    def process_segments(self):
        pend = self.pending_files()
        for k, f in enumerate(pend):
            s = self.heartbeat(); rel = str(f.relative_to(self.dir))
            try:
                self.process_one(s, f, rel, backlog=len(pend) - k - 1)
            except LostLease:
                raise
            except Exception as e:  # um bloco corrompido não derruba a sessão: fica registrado e é ignorado
                log.exception("segmento %s falhou", rel)
                t0 = self.next_t0()
                self.c.execute("INSERT OR IGNORE INTO live_segments(session_id,user_id,seq,path,t_start,duration,wall_start,deleted,created_at) "
                               "VALUES(?,?,?,?,?,0,?,1,?)", (self.sid, s["user_id"], self.next_seq(), rel, t0, db.now(), db.now()))
                f.unlink(missing_ok=True)
                store.event(self.c, s, "segment_error", {"path": rel, "error": str(e)[:200]}, t0)

    def next_seq(self):
        return (self.c.execute("SELECT MAX(seq) FROM live_segments WHERE session_id=?", (self.sid,)).fetchone()[0] or 0) + 1

    def next_t0(self):
        """Tempo da gravação = soma das durações já registradas (fonte de verdade é a tabela, não um contador)."""
        return self.c.execute("SELECT COALESCE(MAX(t_start+duration),0) FROM live_segments WHERE session_id=? AND duration>0",
                              (self.sid,)).fetchone()[0]

    def process_one(self, s, f, rel, backlog):
        dur = ffprobe_duration(f)
        if dur < 0.5:
            self.c.execute("INSERT OR IGNORE INTO live_segments(session_id,user_id,seq,path,t_start,duration,wall_start,deleted,created_at) "
                           "VALUES(?,?,?,?,?,0,?,1,?)", (self.sid, s["user_id"], self.next_seq(), rel, self.next_t0(), db.now(), db.now()))
            f.unlink(missing_ok=True); return
        wall_start = f.stat().st_mtime - dur
        prev = store.preview_path(s["user_id"], s["id"]).with_suffix(".part.jpg")
        kf = ACTIVE_RUNNERS[0] > VISUAL_FULL_MAX
        dbs = engine.detect.loudness(f, 0.5); vis = visual_change(f, preview=prev, keyframes=kf)
        self.vis_step = (dur / max(len(vis), 1)) if kf else 0.5
        # linha de base do áudio: mediana móvel de 5 min; nos primeiros 30 s, a mediana do próprio bloco
        base_a = float(np.median(self.audio_hist)) if len(self.audio_hist) >= 60 else (float(np.median(dbs)) if len(dbs) else -99.0)
        excess = float(dbs.max()) - base_a if len(dbs) else 0.0
        quiet = len(dbs) and excess < AUDIO_DB - 3
        # "events" (padrão): só transcreve blocos com pico de áudio (≥ EVENT_TRANSCRIBE_DB acima da mediana; padrão 6 dB);
        # janelas que vão para o Claude ou viram corte são transcritas sob demanda (ensure_words). "all": todo bloco.
        gate = AUDIO_DB if kf else EVENT_TRANSCRIBE_DB  # kf = agente com muitas sessões: transcreve só picos fortes
        if (s["transcribe_mode"] == "events" and excess < gate) or (backlog >= 2 and quiet):
            raw_words, lang, transcribed = [], s["lang"], False
        else:
            raw_words, lang = transcribe(f, dur, None if s["lang"] == "auto" else s["lang"]); transcribed = True
        if self.layout is None:
            self.layout = engine.webcam_layout(f)
            store.event(self.c, s, "layout", {"webcam": self.layout.get("webcam"), "focus": self.layout.get("focus")}, self.next_t0())
        self.c.execute("BEGIN IMMEDIATE")  # linha do segmento + tempo gravado na mesma transação
        try:
            t0 = self.next_t0(); seq = self.next_seq()
            words = [{"w": w["w"], "s": round(t0 + w["s"], 2), "e": round(t0 + w["e"], 2)} for w in raw_words]
            self.c.execute("INSERT INTO live_segments(session_id,user_id,seq,path,t_start,duration,wall_start,db_max,db_median,vis_max,text,words,"
                           "transcribed,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (self.sid, s["user_id"], seq, rel, t0, dur, wall_start,
                           float(dbs.max()) if len(dbs) else None, float(np.median(dbs)) if len(dbs) else None,
                           float(vis.max()) if len(vis) else None, " ".join(w["w"] for w in words), json.dumps(words), int(transcribed), db.now()))
            self.c.execute("UPDATE live_sessions SET recorded_s=?, updated_at=? WHERE id=?", (t0 + dur, db.now(), self.sid))
            plans.charge_live(self.c, s["user_id"], dur)  # franquia mensal consumida bloco a bloco
            if prev.exists() and prev.stat().st_size > 0:
                prev.replace(store.preview_path(s["user_id"], s["id"]))  # troca atômica: o navegador nunca lê arquivo pela metade
                off = min(max(len(vis) - 1, 0) * self.vis_step, dur)
                self.c.execute("UPDATE live_sessions SET preview_t=?, preview_wall=? WHERE id=?", (round(t0 + off, 2), wall_start + off, self.sid))
            back = self.c.execute("UPDATE live_sessions SET status='running' WHERE id=? AND status='reconnecting'", (self.sid,)).rowcount
            self.c.execute("COMMIT")
        except Exception:
            self.c.execute("ROLLBACK"); raise
        if back:
            store.event(self.c, s, "reconnected", {"offline_s": round(db.now() - (self.down_since or db.now()), 1)}, t0)
        self.down_since = None
        store.event(self.c, s, "segment", {"seq": seq, "t_start": round(t0, 2), "duration": round(dur, 2),
                    "wall_start": round(wall_start, 3), "lag_s": round(db.now() - (wall_start + dur), 1),
                    "words": len(words), "db_max": round(float(dbs.max()), 1) if len(dbs) else None, "lang": lang,
                    "transcribed": transcribed, "backlog": backlog, "bytes": f.stat().st_size, "visual": "keyframes" if kf else "2fps"}, t0)
        self.detect(s, t0, dur, dbs, vis, words, wall_start)

    def detect(self, s, t0, dur, dbs, vis, words, wall_start):
        n = min(len(dbs), int(dur / 0.5) + 1)
        vis = np.interp(np.arange(n) * 0.5, np.arange(len(vis)) * self.vis_step, vis) if len(vis) > 1 else np.zeros(n)
        base_a = np.median(self.audio_hist) if len(self.audio_hist) >= 60 else float(np.median(dbs[:n])) if n else -60
        hv = np.array(self.vis_hist) if len(self.vis_hist) >= 20 else vis
        med_v = float(np.median(hv)) if len(hv) else 0; mad_v = float(np.median(np.abs(hv - med_v))) + 0.5
        best = None
        for i in range(n):
            t = t0 + i * 0.5; a_ex = float(dbs[i] - base_a); v_ex = float((vis[i] - med_v) / mad_v)
            near = " ".join(x["w"].lower() for x in words if t - 1.5 <= x["s"] <= t + 1.5)
            kws = sorted({k for k in KEYWORDS if k in near})
            hit = a_ex >= AUDIO_DB or (kws and a_ex >= 4) or (v_ex >= 6 and vis[i] > 8 and a_ex >= 3)
            if not hit: continue
            score = round(a_ex / 10 + (0.5 if kws else 0) + min(max(v_ex, 0), 10) / 20, 2)
            if best is None or score > best[0]:
                best = (score, t, {"audio_db_above_baseline": round(a_ex, 1), "baseline_db": round(float(base_a), 1),
                                   "visual_change_z": round(v_ex, 1), "keywords": kws, "wall_at": round(wall_start + i * 0.5, 3)})
        self.audio_hist.extend(dbs[:n].tolist()); self.vis_hist.extend(vis.tolist())
        if best and best[1] - self.last_peak >= COOLDOWN_S:
            score, t, sig = best; self.last_peak = t; mid = db.new_id("mom")
            self.c.execute("INSERT INTO live_moments(id,session_id,user_id,peak,w_start,w_end,score,signals,status,source,created_at,updated_at) "
                           "VALUES(?,?,?,?,?,?,?,?,'waiting','auto',?,?)", (mid, self.sid, s["user_id"], round(t, 2), round(max(0, t - PRE_S), 2),
                           round(t + POST_S, 2), score, json.dumps(sig), db.now(), db.now()))
            store.event(self.c, s, "candidate", {"moment_id": mid, "peak": round(t, 2), "score": score, **sig}, t)

    # ------------------------------------------------------------------ momentos e cortes
    def handle_moments(self, s):
        self.c.execute("UPDATE live_moments SET status='ready', updated_at=? WHERE session_id=? AND status='waiting' AND w_end<=?",
                       (db.now(), self.sid, s["recorded_s"]))
        for m in self.c.execute("SELECT * FROM live_moments WHERE session_id=? AND status IN ('clip_pending','clip_requested') AND clip_id='' "
                                "ORDER BY created_at", (self.sid,)).fetchall():
            if m["status"] == "clip_requested" and m["w_end"] > s["recorded_s"]: continue  # ainda não gravado
            try:
                self.create_clip(s, m)
            except Exception as e:
                log.exception("corte %s falhou", m["id"])
                self.c.execute("UPDATE live_moments SET status='clip_failed', error=?, updated_at=? WHERE id=? AND clip_id=''",
                               ("Falha ao preparar o trecho para o render.", db.now(), m["id"]))
                store.event(self.c, s, "clip_failed", {"moment_id": m["id"], "error": str(e)[:200]}, m["peak"])
        for m in self.c.execute("SELECT m.*, c.status AS cstatus, c.updated_at AS cupd, c.created_at AS ccre FROM live_moments m JOIN clips c ON c.id=m.clip_id "
                                "WHERE m.session_id=? AND m.status='clip_queued' AND c.status IN ('ready','failed','approved')", (self.sid,)).fetchall():
            ok = m["cstatus"] != "failed"
            if not self.c.execute("UPDATE live_moments SET status=?, updated_at=? WHERE id=? AND status='clip_queued'",
                                  ("clipped" if ok else "clip_failed", db.now(), m["id"])).rowcount: continue
            sig = json.loads(m["signals"]); peak_wall = sig.get("wall_at") or 0
            auto = m["source"] == "auto"  # latência evento→corte só faz sentido quando ninguém esperou um clique
            store.event(self.c, s, "clip_ready" if ok else "clip_failed", {"moment_id": m["id"], "clip_id": m["clip_id"], "source": m["source"],
                        "peak_wall": peak_wall, "queued_wall": m["ccre"], "ready_wall": m["cupd"], "render_s": round(m["cupd"] - m["ccre"], 1),
                        "event_to_clip_s": round(m["cupd"] - peak_wall, 1) if (peak_wall and auto) else None}, m["peak"])

    def segments_for(self, a, b):
        return self.c.execute("SELECT * FROM live_segments WHERE session_id=? AND duration>0 AND t_start<? AND t_start+duration>? ORDER BY seq",
                              (self.sid, b, a)).fetchall()

    def create_clip(self, s, m):
        dec = json.loads(m["decision"]) if m["decision"] else {}
        a, b = (dec["start_t"], dec["end_t"]) if dec.get("decision") == "clip" else (m["w_start"], m["w_end"])
        u = self.c.execute("SELECT * FROM users WHERE id=?", (s["user_id"],)).fetchone()
        q = plans.live_quota_left(self.c, u) if u else None
        if not q or q[1] <= 0:
            msg = "Franquia de cortes do mês esgotada." if q else "Conta sem plano ativo."
            self.c.execute("UPDATE live_moments SET status='clip_failed', error=?, updated_at=? WHERE id=? AND clip_id=''", (msg, db.now(), m["id"]))
            store.event(self.c, s, "clip_failed", {"moment_id": m["id"], "error": msg}, m["peak"]); return
        ensure_words(self.c, self.sid, self.dir, s["lang"], a, b)
        segs = self.segments_for(a, b)
        if not segs or any(x["deleted"] for x in segs) or segs[0]["t_start"] > a + 0.5:
            self.c.execute("UPDATE live_moments SET status='clip_failed', error=?, updated_at=? WHERE id=? AND clip_id=''",
                           ("Trecho fora do buffer de gravação.", db.now(), m["id"]))
            store.event(self.c, s, "clip_failed", {"moment_id": m["id"], "error": "Trecho fora do buffer de gravação."}, m["peak"]); return
        pdir = db.user_dir(s["user_id"]) / "projects" / s["project_id"] / "live"; pdir.mkdir(parents=True, exist_ok=True)
        lst = pdir / f"{m['id']}.txt"; out = pdir / f"{m['id']}.mp4"; tmp = pdir / f"{m['id']}.part.mp4"
        lst.write_text("".join(f"file {shlex.quote(str(self.dir / x['path']))}\n" for x in segs))
        # MP4 com timestamps zerados: o render do motor usa seek de entrada (-ss antes de -i), confiável em MP4
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-bsf:a", "aac_adtstoasc",
                        "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", "-f", "mp4", str(tmp)], check=True, timeout=120)
        lst.unlink(missing_ok=True); base = segs[0]["t_start"]
        words = [{"w": w["w"], "s": round(w["s"] - a, 2), "e": round(w["e"] - a, 2)}
                 for x in segs for w in json.loads(x["words"]) if a <= w["s"] and w["e"] <= b]
        lay = self.layout or {"webcam": None}
        data = {"id": m["id"], "src": f"live/{out.name}", "lang": s["lang"], "kind": "live", "start": round(a - base, 2),
                "end": round(b - base, 2), "peak": round(min(max(m["peak"] - a, 0), b - a), 2), "strength": m["score"],
                "words": words, "webcam": lay.get("webcam"), **({"focus": lay["focus"]} if lay.get("focus") is not None else {})}
        fb = copywriter.fallback({"words": words})
        cp = ({**fb, "screen_title": dec["screen_title"], "title": dec["title"], "description": dec["summary"], "source": "claude"}
              if dec.get("decision") == "clip" else {**fb, "source": "manual" if m["source"] == "manual" else "padrao"})
        cid = db.new_id("clip"); t = db.now()
        self.c.execute("BEGIN IMMEDIATE")  # corte + job + momento: tudo ou nada (sem corte duplicado após queda)
        try:
            if not self.c.execute("SELECT 1 FROM live_moments WHERE id=? AND clip_id='' AND status IN ('clip_pending','clip_requested')",
                                  (m["id"],)).fetchone():
                self.c.execute("ROLLBACK"); tmp.unlink(missing_ok=True); return
            q = plans.live_quota_left(self.c, u) if u else None  # rechecagem dentro da transação: sessões paralelas não estouram a franquia
            if not q or q[1] <= 0:
                self.c.execute("ROLLBACK"); tmp.unlink(missing_ok=True)
                self.c.execute("UPDATE live_moments SET status='clip_failed', error=?, updated_at=? WHERE id=? AND clip_id=''",
                               ("Franquia de cortes do mês esgotada.", db.now(), m["id"])); return
            tmp.replace(out)
            idx = (self.c.execute("SELECT MAX(idx) FROM clips WHERE project_id=?", (s["project_id"],)).fetchone()[0] or 0) + 1
            self.c.execute('INSERT INTO clips(id,user_id,project_id,idx,start,"end",peak,strength,data,copy,status,created_at,updated_at) '
                           "VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?)", (cid, s["user_id"], s["project_id"], idx, a, b, m["peak"], m["score"],
                           json.dumps(data), json.dumps(cp, ensure_ascii=False), t, t))
            enqueue(self.c, s["user_id"], "render", s["project_id"], cid)
            plans.count_live_clip(self.c, s["user_id"])
            self.c.execute("UPDATE live_moments SET status='clip_queued', clip_id=?, updated_at=? WHERE id=?", (cid, t, m["id"]))
            self.c.execute("COMMIT")
        except Exception:
            self.c.execute("ROLLBACK"); raise
        store.event(self.c, s, "clip_queued", {"moment_id": m["id"], "clip_id": cid, "start_t": a, "end_t": b,
                                                "source": cp["source"], "screen_title": cp["screen_title"]}, m["peak"])

    def retention(self, s):
        keep_from = s["recorded_s"] - BUFFER_S
        need = self.c.execute("SELECT MIN(w_start) FROM live_moments WHERE session_id=? AND status IN "
                              "('waiting','ready','analyzing','clip_pending','clip_requested')", (self.sid,)).fetchone()[0]
        if need is not None: keep_from = min(keep_from, need - 1)
        for x in self.c.execute("SELECT * FROM live_segments WHERE session_id=? AND deleted=0 AND t_start+duration<?", (self.sid, keep_from)).fetchall():
            (self.dir / x["path"]).unlink(missing_ok=True)
            self.c.execute("UPDATE live_segments SET deleted=1 WHERE session_id=? AND seq=?", (self.sid, x["seq"]))

    def finalize(self, reason):
        if self.proc: kill_group(self.proc.pid); self.proc.wait(10)
        self.run_dir = None
        if self.analyzer: self.analyzer.stop = True
        for step in (self.process_segments, lambda: self.handle_moments(self.session())):
            try: step()
            except LostLease: raise
            except Exception: log.exception("finalização parcial (sessão %s)", self.sid)
        s = self.session()
        self.c.execute("UPDATE live_moments SET status='expired', updated_at=? WHERE session_id=? AND status IN "
                       "('waiting','ready','analyzing','clip_pending','clip_requested')", (db.now(), self.sid))
        for x in self.c.execute("SELECT * FROM live_segments WHERE session_id=? AND deleted=0", (self.sid,)).fetchall():
            (self.dir / x["path"]).unlink(missing_ok=True)
        self.c.execute("UPDATE live_segments SET deleted=1 WHERE session_id=?", (self.sid,))
        shutil.rmtree(self.dir / "segments", ignore_errors=True)
        for f in self.dir.glob("preview*.jpg"): f.unlink(missing_ok=True)  # retenção: nada da transmissão bruta fica após encerrar
        store.update_session(self.c, self.sid, status="stopped", stopped_at=db.now(), locked_until=0, recorder_pgid=0)
        self.c.execute("UPDATE projects SET status='done', updated_at=? WHERE id=? AND status='live'", (db.now(), s["project_id"]))
        store.event(self.c, s, "stopped", {"reason": reason, "recorded_s": round(s["recorded_s"], 1), "calls": s["calls"],
                                           "spent_usd": round(s["spent_usd"], 4)}, s["recorded_s"])
        log.info("sessão %s encerrada (%s)", self.sid, reason)


class Analyzer(threading.Thread):
    """Envia momentos prontos à Claude API sem bloquear a gravação. Aplica orçamento, intervalo e redução de frames."""
    def __init__(self, sid):
        super().__init__(daemon=True, name=f"claude-{sid}"); self.sid = sid; self.stop = False

    def run(self):
        with db.conn() as c:
            self.c = c
            while not self.stop and not _stop:
                try:
                    if not self.step(): time.sleep(1)
                except Exception:
                    log.exception("análise falhou (sessão %s)", self.sid); time.sleep(3)

    def step(self):
        c = self.c; s = c.execute("SELECT * FROM live_sessions WHERE id=?", (self.sid,)).fetchone()
        if not s or s["status"] not in ("running", "reconnecting") or s["worker"] != AGENT: return False
        ready = c.execute("SELECT * FROM live_moments WHERE session_id=? AND status='ready' ORDER BY peak", (self.sid,)).fetchall()
        if not ready: return False
        st, detail = claude_live.status()
        if st == "ready" and s["budget_usd"] <= 0:  # o usuário escolheu orçamento zero: nenhuma chamada à IA nesta sessão
            st, detail = "disabled", "Análise de IA desligada nesta sessão (orçamento de US$ 0)."
        if st != "ready":
            for m in ready:
                if c.execute("UPDATE live_moments SET status='candidate', error=?, updated_at=? WHERE id=? AND status='ready'",
                             (detail, db.now(), m["id"])).rowcount:
                    store.event(c, s, "analysis_skipped", {"moment_id": m["id"], "reason": detail}, m["peak"])
            store.update_session(c, self.sid, claude_state="disabled", claude_detail=detail)
            return True
        if len(ready) > MAX_QUEUE:  # fila cheia: fica com os de maior score
            keep = {m["id"] for m in sorted(ready, key=lambda m: -m["score"])[:MAX_QUEUE]}
            for m in ready:
                if m["id"] not in keep and c.execute("UPDATE live_moments SET status='skipped', error='Fila de análise cheia.', updated_at=? "
                                                     "WHERE id=? AND status='ready'", (db.now(), m["id"])).rowcount:
                    store.event(c, s, "analysis_skipped", {"moment_id": m["id"], "reason": "Fila de análise cheia (limite de chamadas)."}, m["peak"])
            ready = [m for m in ready if m["id"] in keep]
        if db.now() - s["last_call_at"] < MIN_CALL_INTERVAL: return False
        m = ready[0]
        try:
            self.analyze(s, m)
        except Exception as e:  # nunca deixa um momento preso em 'analyzing' (isso travaria a limpeza do buffer)
            log.exception("análise do momento %s falhou", m["id"])
            if c.execute("UPDATE live_moments SET status='candidate', error=?, updated_at=? WHERE id=? AND status IN ('ready','analyzing')",
                         ("Falha interna na análise.", db.now(), m["id"])).rowcount:
                store.event(c, s, "claude_error", {"moment_id": m["id"], "error": f"Falha interna: {str(e)[:150]}"}, m["peak"])
        return True

    def frames(self, s, m, n):
        times = {1: [m["peak"]], 2: [m["peak"] - 1.5, m["peak"] + 1.5], 3: [m["peak"] - 3, m["peak"], m["peak"] + 2.5]}[n]
        out = []; d = store.session_dir(s["user_id"], s["id"])
        q = "SELECT * FROM live_segments WHERE session_id=? AND deleted=0 AND duration>0 AND {} ORDER BY seq {} LIMIT 1"
        for t in times:
            seg = self.c.execute(q.format("t_start<=? AND t_start+duration>?", ""), (self.sid, t, t)).fetchone()
            if not seg: continue
            nxt = self.c.execute(q.format("t_start>?", "ASC"), (self.sid, seg["t_start"])).fetchone()
            off = t - seg["t_start"]
            # a trilha de vídeo do .ts termina um pouco antes da duração do contêiner: se não houver frame no fim do bloco,
            # usa o primeiro frame do bloco seguinte ou um pouco antes — e registra o tempo REAL do frame usado
            for sg, o in ((seg, off), (nxt, 0.0), (seg, max(0.0, off - 0.6))):
                data = extract_frame(d / sg["path"], o) if sg else None
                if data:
                    out.append((round(sg["t_start"] + o, 2), sg["wall_start"] + o, data)); break
        return out

    def transcript(self, a, b):
        segs = self.c.execute("SELECT words FROM live_segments WHERE session_id=? AND t_start<? AND t_start+duration>? ORDER BY seq", (self.sid, b, a))
        ws = [w for x in segs for w in json.loads(x["words"]) if a <= w["s"] < b]
        lines, cur = [], []
        for w in ws:
            if cur and w["s"] - cur[0]["s"] > 3: lines.append(cur); cur = []
            cur.append(w)
        if cur: lines.append(cur)
        return "\n".join(f"[t={g[0]['s']:.1f}] " + " ".join(x["w"] for x in g) for g in lines)

    def charge(self, cost, calls=1):
        """Gasto/chamadas somados no banco (atômico: não perde atualização entre threads/agentes) e na franquia mensal de IA."""
        self.c.execute("UPDATE live_sessions SET spent_usd=ROUND(spent_usd+?, 6), calls=calls+?, updated_at=? WHERE id=?",
                       (cost, calls, db.now(), self.sid))
        if cost:
            uid = self.c.execute("SELECT user_id FROM live_sessions WHERE id=?", (self.sid,)).fetchone()[0]
            plans.charge_ai(self.c, uid, cost)

    def analyze(self, s, m):
        c = self.c; frac = s["spent_usd"] / max(s["budget_usd"], 1e-9)
        n = 3 if frac < 0.5 else 2 if frac < 0.8 else 1  # redução de frames conforme o orçamento é consumido
        ensure_words(c, self.sid, store.session_dir(s["user_id"], s["id"]), s["lang"], max(0, m["w_start"] - 90), m["w_end"])
        frames = self.frames(s, m, n); text = self.transcript(m["w_start"], m["w_end"])
        ctx = self.transcript(max(0, m["w_start"] - 90), m["w_start"])[-1500:]
        est = claude_live.estimate(len(frames), len(text) + len(ctx))
        u = c.execute("SELECT * FROM users WHERE id=?", (s["user_id"],)).fetchone()
        if not u or plans.ai_left(c, u) < est:  # teto mensal de IA do plano: o momento fica como candidato; a gravação continua
            msg = "Orçamento mensal de IA do plano esgotado."
            if c.execute("UPDATE live_moments SET status='candidate', error=?, updated_at=? WHERE id=? AND status='ready'", (msg, db.now(), m["id"])).rowcount:
                store.event(c, s, "analysis_skipped", {"moment_id": m["id"], "reason": msg, "estimate_usd": est}, m["peak"])
            store.update_session(c, self.sid, claude_state="disabled", claude_detail=msg)
            return
        if s["spent_usd"] + est > s["budget_usd"] or s["calls"] + 1 > s["max_calls"]:
            reason = "budget" if s["spent_usd"] + est > s["budget_usd"] else "calls"
            c.execute("UPDATE live_moments SET status='skipped', error=?, updated_at=? WHERE id=? AND status='ready'",
                      ("Orçamento da sessão esgotado." if reason == "budget" else "Limite de chamadas atingido.", db.now(), m["id"]))
            if c.execute("UPDATE live_sessions SET status='stopping', stop_reason=?, updated_at=? WHERE id=? AND status IN ('running','reconnecting')",
                         (reason, db.now(), self.sid)).rowcount:
                store.event(c, s, "limit", {"reason": reason, "estimate_usd": est, "spent_usd": s["spent_usd"]}, m["peak"])
            return
        if not frames:
            c.execute("UPDATE live_moments SET status='skipped', error='Sem frames no buffer.', updated_at=? WHERE id=? AND status='ready'",
                      (db.now(), m["id"])); return
        if not c.execute("UPDATE live_moments SET status='analyzing', updated_at=? WHERE id=? AND status='ready'", (db.now(), m["id"])).rowcount:
            return
        sig = json.loads(m["signals"])
        store.event(c, s, "analysis_started", {"moment_id": m["id"], "frames_planned": n, "frames_t": [f[0] for f in frames],
                                                "estimate_usd": est, "spent_before_usd": s["spent_usd"]}, m["peak"])
        store.update_session(c, self.sid, last_call_at=db.now(), claude_state="calling", claude_detail=claude_live.MODEL)
        c.execute("BEGIN IMMEDIATE")  # reserva atômica do pior caso no teto mensal de IA
        if plans.ai_left(c, u) < est:
            c.execute("ROLLBACK")
            c.execute("UPDATE live_moments SET status='candidate', error=?, updated_at=? WHERE id=? AND status='analyzing'",
                      ("Orçamento mensal de IA do plano esgotado.", db.now(), m["id"])); return
        plans.charge_ai(c, s["user_id"], est); c.execute("COMMIT")
        try:
            dec, meta = claude_live.analyze(frames, (m["w_start"], m["w_end"]), text, ctx, sig)
        except claude_live.ClaudeUnavailable as e:
            plans.charge_ai(c, s["user_id"], -est)
            self.charge(0, 1)  # a requisição saiu do servidor; conta a chamada (custo desconhecido = 0)
            c.execute("UPDATE live_moments SET status='candidate', error=?, updated_at=? WHERE id=? AND status='analyzing'", (str(e), db.now(), m["id"]))
            store.update_session(c, self.sid, claude_state="error", claude_detail=str(e))
            store.event(c, s, "claude_error", {"moment_id": m["id"], "error": str(e)}, m["peak"]); return
        except claude_live.InvalidDecision as e:
            plans.charge_ai(c, s["user_id"], -est); meta = e.meta or {}
            if meta: self.charge(meta.get("cost_usd", 0), 1)
            c.execute("UPDATE live_moments SET status='invalid', error=?, updated_at=? WHERE id=? AND status='analyzing'", (str(e), db.now(), m["id"]))
            store.update_session(c, self.sid, claude_state="ok" if meta else "error", claude_detail=str(e))
            store.event(c, s, "analysis_invalid", {"moment_id": m["id"], "error": str(e), **meta}, m["peak"]); return
        plans.charge_ai(c, s["user_id"], -est)  # devolve a reserva; o custo real entra abaixo
        self.charge(meta["cost_usd"], 1)  # gasto registrado assim que a API responde
        saved = []
        for (t, wall, data), sha in zip(frames, meta["frames_sha256"]):
            fid = db.new_id("frm"); p = store.session_dir(s["user_id"], s["id"]) / "frames" / f"{fid}.jpg"; p.write_bytes(data)
            c.execute("INSERT INTO live_frames VALUES(?,?,?,?,?,?,?,?)", (fid, self.sid, s["user_id"], m["id"], t, str(p.relative_to(db.DATA)), sha, db.now()))
            saved.append({"id": fid, "t": t, "wall": round(wall, 3), "sha256": sha})
        go = dec["decision"] == "clip" and dec["confidence"] >= s["min_confidence"]
        moved = c.execute("UPDATE live_moments SET status=?, decision=?, updated_at=? WHERE id=? AND status='analyzing'",
                          ("clip_pending" if go else "rejected", json.dumps(dec, ensure_ascii=False), db.now(), m["id"])).rowcount
        s = c.execute("SELECT * FROM live_sessions WHERE id=?", (self.sid,)).fetchone()
        eid = store.event(c, s, "analysis", {"moment_id": m["id"], "decision": dec["decision"], "confidence": dec["confidence"],
                          "start_t": dec["start_t"], "end_t": dec["end_t"], "screen_title": dec["screen_title"], "reason": dec["reason"],
                          "summary": dec["summary"], "events": dec["events"], "frames": saved, "will_clip": go and bool(moved),
                          "detect_wall": sig.get("wall_at"), **meta}, m["peak"])
        store.update_session(c, self.sid, claude_state="ok", claude_detail=f"{meta['model']} · {meta['latency_s']} s", last_analysis_id=eid)


def claim(c):
    t = db.now()
    return c.execute("""UPDATE live_sessions SET worker=?, locked_until=?, updated_at=? WHERE id=(
        SELECT id FROM live_sessions WHERE status IN ('starting','running','reconnecting','stopping') AND locked_until<?
        ORDER BY created_at LIMIT 1) AND locked_until<? RETURNING id""", (AGENT, t + LEASE_S, t, t, t)).fetchone()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init(); runners = {}
    def stop(*_):
        global _stop; _stop = True
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    log.info("live agent %s pronto · claude=%s", AGENT, claude_live.status())
    with db.conn() as c:
        while not _stop:
            for sid in [k for k, r in runners.items() if r.done]: runners.pop(sid)
            ACTIVE_RUNNERS[0] = len(runners)
            if len(runners) < MAX_SESSIONS:
                row = claim(c)
                if row and row["id"] not in runners:
                    runners[row["id"]] = Runner(row["id"]); runners[row["id"]].start()
            time.sleep(2)
    for r in runners.values():
        if r.proc: kill_group(r.proc.pid)


if __name__ == "__main__": main()
