"use strict";
/* Claude Live Monitor — tudo aqui vem do backend (REST + SSE). Nada é simulado no navegador. */
const LSTATUS = { starting: ["Iniciando", "run"], running: ["Gravando", "ok"], reconnecting: ["Reconectando", "warn"], stopping: ["Encerrando", "warn"], stopped: ["Encerrada", ""] };
const STOPR = { user: "parada por você", duration: "limite de duração", budget: "orçamento esgotado", calls: "limite de chamadas", offline: "live offline", error: "erro no agente" };
const CLAUDE = { disabled: ["Desconectado", "bad"], idle: ["Pronto, aguardando momento", "warn"], calling: ["Analisando agora", "run"], ok: ["Conectado", "ok"], error: ["Erro na API", "bad"] };
const MSTATUS = { waiting: "Gravando o pós-evento", ready: "Na fila do Claude", analyzing: "Claude analisando", candidate: "Candidato (sem análise)", rejected: "Claude descartou",
  clip_pending: "Claude aprovou · cortando", clip_requested: "Corte solicitado", clip_queued: "Renderizando", clipped: "Corte pronto", clip_failed: "Falha no corte",
  skipped: "Não analisado", invalid: "Resposta inválida", expired: "Expirado" };
const fmtT = (t) => { t = Math.max(0, Math.round(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0"); };
const clock = (w) => w ? new Date(w * 1000).toLocaleTimeString("pt-BR") : "—";
const usd = (v) => "US$ " + (v || 0).toFixed(v < 0.1 ? 4 : 2);

function claudeChip(cl) { const [t, k] = CLAUDE[cl.state] || [cl.state, ""]; return `<span class="chip ${k}">Claude: ${esc(t)}</span>`; }

function liveDashCard(sessions, me) {
  const act = sessions.find((s) => s.status !== "stopped"); const cs = me.live_claude || {};
  const claude = cs.state === "ready" ? `<span class="chip ok">Claude API configurada</span>` : `<span class="chip bad">Claude desconectado</span>`;
  const body = act ? `<div class="row"><span class="chip ${LSTATUS[act.status][1]}">${LSTATUS[act.status][0]}</span><strong>twitch.tv/${esc(act.channel)}</strong>
      <span class="muted">${fmtT(act.recorded_s)} gravados · ${act.calls} análises · ${usd(act.spent_usd)}</span><span class="spacer"></span>
      <a class="btn primary" href="/live/${esc(act.id)}" data-link>${icon("radio")}Abrir monitor</a></div>`
    : `<div class="row"><p class="muted">Monitore uma live da Twitch: o agente grava, detecta momentos e o Claude analisa frames e falas reais para sugerir cortes.</p>
      <span class="spacer"></span><a class="btn primary" href="/live" data-link>${icon("radio")}Iniciar monitoramento</a></div>`;
  return `<section class="panel live-dash stack" aria-labelledby="ldh"><div class="row"><h2 id="ldh">Claude Live Monitor</h2><span class="spacer"></span>${claude}</div>
    ${cs.state === "ready" ? "" : `<p class="muted small">${esc(cs.detail || "")} A gravação e a detecção funcionam; a análise do Claude fica desativada até a chave ser configurada.</p>`}${body}</section>`;
}

async function liveHome() {
  const [sessions, me] = await Promise.all([api("/api/live/sessions"), api("/api/me")]); S.me = me; const L = me.limits; const cs = me.live_claude || {};
  const act = sessions.find((s) => s.status !== "stopped");
  if (act) return go(`/live/${act.id}`);
  const past = sessions.map((s) => `<a class="proj" href="/live/${esc(s.id)}" data-link><div class="cover live-cover">${icon("radio")}</div><div class="meta"><h3>twitch.tv/${esc(s.channel)}</h3>
    <div class="sub"><span>${fmtT(s.recorded_s)} gravados</span><span>${s.calls} análises</span><span>${usd(s.spent_usd)}</span><span>${ago(s.created_at)}</span></div></div>
    <span class="chip">${esc(STOPR[s.stop_reason] || LSTATUS[s.status][0])}</span></a>`).join("");
  render(shell("/live", `<div class="page-head"><div><h1>Claude Live Monitor</h1><p>Gravação contínua da live, detecção de momentos e análise do Claude com os frames realmente enviados.</p></div></div>
    <div class="new-grid"><form class="panel stack" id="lf">
      <div class="row">${cs.state === "ready" ? '<span class="chip ok">Claude API configurada</span>' : '<span class="chip bad">Claude desconectado</span>'}</div>
      ${cs.state === "ready" ? "" : `<p class="muted">${esc(cs.detail)} Você ainda pode gravar e ver os momentos candidatos detectados por áudio, imagem e fala, e criar cortes manualmente.</p>`}
      <div class="field"><label for="lch">Canal da Twitch</label><div class="row"><input class="input grow" id="lch" placeholder="twitch.tv/canal" autocomplete="off">
        <button class="btn" type="button" id="lck">Verificar</button></div><span class="hint" id="lst" aria-live="polite"></span></div>
      <div class="two"><div class="field"><label for="lbud">Orçamento de IA (US$)</label><input class="input" id="lbud" type="number" min="0" step="0.05" max="${L ? L.live_budget_usd_max : 0}" value="${L ? Math.min(0.5, L.live_budget_usd_max) : 0}">
        <span class="hint">Máximo do plano: US$ ${L ? L.live_budget_usd_max.toFixed(2) : "0"}. A sessão para sozinha ao atingir.</span></div>
      <div class="field"><label for="lmin">Duração máxima (min)</label><input class="input" id="lmin" type="number" min="1" max="${L ? L.live_max_minutes : 0}" value="${L ? Math.min(30, L.live_max_minutes) : 0}">
        <span class="hint">Até ${L ? L.live_max_minutes : 0} min no seu plano.</span></div></div>
      <div class="field"><label for="llang">Idioma da live</label><select class="input" id="llang">${Object.entries(LANG).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
      <p class="error-text" id="lerr" role="alert"></p>
      <button class="btn primary lg" id="lgo" type="submit" ${L ? "" : "disabled"}>${icon("play")}Iniciar monitoramento</button></form>
    <aside class="panel stack"><h3>Como funciona</h3><ol class="steps compact"><li><b>1</b>O agente grava a live em blocos de 10 s no servidor.</li>
      <li><b>2</b>Cada bloco é transcrito e medido (volume, mudança de imagem, palavras).</li>
      <li><b>3</b>Nos picos, até 3 frames e a fala do trecho vão para o Claude, que responde com decisão, horários e justificativa.</li>
      <li><b>4</b>Cortes aprovados são renderizados enquanto a gravação continua.</li></ol>
      <p class="muted small">O Claude só vê os frames e trechos de fala enviados — cada um aparece no monitor com o horário exato.</p></aside></div>
    ${sessions.length ? `<h2 class="section-title">Sessões anteriores</h2><div class="projects">${past}</div>` : ""}`));
  const chk = async () => {
    $("#lst").textContent = "Consultando a Twitch…";
    try { const r = await api(`/api/live/channel?q=${encodeURIComponent($("#lch").value)}`); $("#lst").textContent = r.live ? `Ao vivo: ${r.title || ""} · ${r.category || ""}` : (r.error || "Este canal não está ao vivo agora."); return r; }
    catch (e) { $("#lst").textContent = e.message; return null; }
  };
  $("#lck").onclick = chk;
  $("#lf").onsubmit = async (e) => {
    e.preventDefault(); $("#lerr").textContent = ""; $("#lgo").disabled = true;
    try {
      const r = await chk(); if (!r || !r.live) throw new Error("O canal precisa estar ao vivo para iniciar.");
      const s = await api("/api/live/sessions", { method: "POST", json: { channel: $("#lch").value, budget_usd: +$("#lbud").value, max_minutes: +$("#lmin").value, lang: $("#llang").value } });
      go(`/live/${s.id}`);
    } catch (err) { $("#lerr").textContent = err.message; $("#lgo").disabled = false; }
  };
}

const KIND = {
  created: (d) => `Sessão criada · orçamento ${usd(d.budget_usd)} · até ${d.max_minutes} min`,
  started: () => "Agente iniciou a gravação", resumed: () => "Sessão retomada por outro agente após falha",
  layout: (d) => d.webcam ? "Webcam detectada no canto da tela" : "Sem webcam: enquadramento de tela cheia",
  candidate: (d) => `Momento candidato · áudio ${d.audio_db_above_baseline > 0 ? "+" : ""}${d.audio_db_above_baseline} dB${d.keywords.length ? " · “" + d.keywords.join("”, “") + "”" : ""}${d.visual_change_z >= 6 ? " · mudança de imagem" : ""}`,
  analysis_started: (d) => `Enviado ao Claude: ${d.frames_t.length} frame(s) em t=${d.frames_t.map(fmtT).join(", ")} + transcrição`,
  analysis: (d) => `Claude: ${d.decision === "clip" ? "CORTAR" : "IGNORAR"} (${Math.round(d.confidence * 100)}%) · ${d.reason}`,
  analysis_invalid: (d) => `Resposta do Claude rejeitada na validação: ${d.error}`, analysis_skipped: (d) => `Não analisado: ${d.reason}`,
  claude_error: (d) => `Falha ao chamar o Claude: ${d.error}`, clip_requested: () => "Corte solicitado",
  clip_queued: (d) => `Corte enviado ao render (${fmtT(d.start_t)}–${fmtT(d.end_t)}) · ${d.screen_title}`,
  clip_ready: (d) => `Corte pronto · render ${d.render_s}s${d.event_to_clip_s ? ` · ${d.event_to_clip_s}s do evento na live até o corte` : ""}`, clip_failed: (d) => `Falha no corte: ${d.error || ""}`,
  disconnected: () => "Transmissão desconectada · tentando reconectar", reconnected: (d) => `Reconectado após ${d.offline_s}s`,
  limit: (d) => `Limite atingido: ${STOPR[d.reason] || d.reason}`, stop_requested: () => "Parada solicitada", stopped: (d) => `Sessão encerrada (${STOPR[d.reason] || d.reason})`,
};

async function liveSession(sid) {
  const s = await api(`/api/live/sessions/${encodeURIComponent(sid)}`);
  const host = location.hostname;
  render(shell("/live", `<div class="page-head"><div><a href="/live" data-link class="back">${icon("back")}Live Monitor</a><h1>twitch.tv/${esc(s.channel)}</h1>
      <p id="lmeta"></p></div><div class="row" id="lhead"></div></div>
    <div class="live-grid">
      <section class="stack">
        <div class="tw"><iframe title="Transmissão ao vivo na Twitch" src="https://player.twitch.tv/?channel=${encodeURIComponent(s.channel)}&parent=${encodeURIComponent(host)}&muted=true&autoplay=true" allowfullscreen></iframe></div>
        <div class="panel stack" id="lclaude"></div>
        <div class="panel stack"><div class="row"><h2>Cortes</h2><span class="spacer"></span><span class="muted small" id="lclipsn"></span></div><div class="clips" id="lclips"></div></div>
      </section>
      <aside class="stack">
        <div class="panel stack"><div class="row"><h2>Momentos</h2><span class="spacer"></span><span class="muted small" id="lmomn"></span></div><div id="lmoments" class="moments"></div></div>
        <div class="panel stack"><div class="row"><h2>Linha do tempo</h2><span class="spacer"></span><span class="muted small" id="lseg"></span></div><ol id="ltl" class="timeline" aria-live="off"></ol></div>
      </aside></div>`));
  const tl = $("#ltl"); let cur = s, segN = 0, lastSeg = null, clipKey = "";
  const addEv = (e) => {
    if (e.kind === "segment") { segN++; lastSeg = e; $("#lseg").textContent = `${segN} blocos de 10 s · atraso ${e.data.lag_s}s · último ${clock(e.wall_at)}`; return; }
    const f = KIND[e.kind]; const li = document.createElement("li"); li.className = `ev ev-${e.kind}`;
    li.innerHTML = `<div class="ev-t"><b>${e.t_stream != null ? fmtT(e.t_stream) : "—"}</b><span>${clock(e.wall_at)}</span></div><div class="ev-b">${esc(f ? f(e.data) : e.kind)}</div>`;
    tl.prepend(li); while (tl.children.length > 150) tl.lastChild.remove();
  };
  const paint = async (x) => {
    cur = x; const [st, k] = LSTATUS[x.status] || [x.status, ""];
    $("#lhead").innerHTML = `<span class="chip ${k}">${st}${x.status === "stopped" && x.stop_reason ? " · " + esc(STOPR[x.stop_reason] || x.stop_reason) : ""}</span>
      ${["starting", "running", "reconnecting"].includes(x.status) ? `<button class="btn danger" id="lstop">${icon("stop")}Parar monitoramento</button>` : ""}`;
    $("#lmeta").textContent = `${fmtT(x.recorded_s)} gravados de ${x.max_minutes} min · agente ${x.agent_alive || x.status === "stopped" ? "ativo" : "sem sinal"}`;
    $("#lstop")?.addEventListener("click", async () => { if (!confirm("Parar o monitoramento desta live?")) return; try { paint(await api(`/api/live/sessions/${sid}/stop`, { method: "POST" })); } catch (e) { toast(e.message, true); } });
    const la = x.last_analysis, cl = x.claude; const mid = la && la.frames.length ? la.frames[Math.floor(la.frames.length / 2)] : null;
    $("#lclaude").innerHTML = `<div class="row"><h2>Análise do Claude</h2><span class="spacer"></span>${claudeChip(cl)}</div>
      ${cl.state === "disabled" ? `<p class="notice bad">${esc(cl.detail)} Nenhum frame é enviado à IA nesta sessão; os momentos ficam como candidatos.</p>` : `<p class="muted small">${esc(cl.detail || "")}${cl.last_call_at ? " · última chamada " + clock(cl.last_call_at) : ""}</p>`}
      <div class="claude-grid"><figure class="lframe">${mid ? `<img src="/api/live/frames/${esc(mid.id)}" alt="Último frame enviado ao Claude, t=${fmtT(mid.t)}">
          <figcaption>Último frame enviado à IA · t=${fmtT(mid.t)} da gravação · ${clock(mid.wall)} · sha256 ${esc(mid.sha256.slice(0, 12))}…</figcaption>`
          : `<div class="lframe-empty">${cl.state === "disabled" ? "Claude desconectado: nenhum frame enviado" : "Nenhum frame enviado ainda"}</div>`}</figure>
        <div class="stack">${la ? `<div><span class="muted small">Última análise · ${clock(la.at)} · t=${fmtT(la.t_stream)} · ${la.latency_s}s · ${usd(la.cost_usd)}</span>
          <h3>${la.decision === "clip" ? "Cortar" : "Ignorar"} · ${Math.round(la.confidence * 100)}%</h3><p>${esc(la.summary)}</p><p class="muted">${esc(la.reason)}</p></div>` : `<p class="muted">Sem análises ainda.</p>`}
          <div class="field"><span class="muted small">Orçamento: ${usd(x.spent_usd)} de ${usd(x.budget_usd)}</span><progress max="${x.budget_usd || 1}" value="${x.spent_usd}"></progress>
          <span class="muted small">Chamadas: ${x.calls} de ${x.max_calls}</span></div></div></div>`;
    const ms = x.moments || []; $("#lmomn").textContent = `${ms.length} detectados`;
    const can = ["running", "reconnecting"].includes(x.status);
    $("#lmoments").innerHTML = ms.length ? ms.map((m) => `<article class="mom mom-${esc(m.status)}"><div class="row"><b>t=${fmtT(m.peak)}</b><span class="muted small">${clock(m.signals.wall_at)}</span><span class="spacer"></span><span class="chip">${esc(MSTATUS[m.status] || m.status)}</span></div>
        <p class="small muted">${m.signals.manual ? "Intervalo manual" : `Áudio ${m.signals.audio_db_above_baseline > 0 ? "+" : ""}${m.signals.audio_db_above_baseline} dB sobre a média${m.signals.keywords?.length ? " · “" + esc(m.signals.keywords.join("”, “")) + "”" : ""}`}</p>
        ${m.decision ? `<p><b>${esc(m.decision.screen_title)}</b> — ${esc(m.decision.reason)}</p>` : ""}${m.error ? `<p class="small muted">${esc(m.error)}</p>` : ""}
        ${can && !m.clip_id && ["candidate", "rejected", "skipped", "invalid"].includes(m.status) ? `<button class="btn" data-mclip="${esc(m.id)}">${icon("scissors")}Criar corte</button>` : ""}</article>`).join("")
      : `<p class="muted">Nenhum momento ainda. Picos de áudio, mudanças bruscas de imagem e palavras de reação viram candidatos.</p>`;
    $$("[data-mclip]").forEach((b) => b.onclick = async () => { b.disabled = true; try { await api(`/api/live/sessions/${sid}/clips`, { method: "POST", json: { moment_id: b.dataset.mclip } }); toast("Corte solicitado ao agente."); } catch (e) { toast(e.message, true); b.disabled = false; } });
    const key = ms.filter((m) => m.clip_id).map((m) => m.clip_id + m.clip_status).join();
    if (key !== clipKey) { clipKey = key; await paintClips(x); }
  };
  const paintClips = async (x) => {
    const p = await api(`/api/projects/${x.project_id}`).catch(() => null); if (!p) return;
    $("#lclipsn").textContent = `${p.items.length} cortes`;
    $("#lclips").innerHTML = p.items.length ? p.items.map(clipCard).join("") : `<p class="muted">Os cortes aparecem aqui com preview assim que o render termina.</p>`;
    $$("#lclips [data-act]").forEach((b) => b.addEventListener("click", async () => {
      const c = p.items.find((i) => i.id === b.dataset.id); if (b.dataset.act === "edit") return editor(c, null);
      b.disabled = true; try { await api(`/api/clips/${b.dataset.id}/${b.dataset.act}`, { method: "POST" }); clipKey = ""; paint(cur); } catch (e) { toast(e.message, true); b.disabled = false; }
    }));
  };
  await paint(s);
  const es = new EventSource(`/api/live/sessions/${encodeURIComponent(sid)}/events`); S.es = es;
  es.addEventListener("live", (m) => addEv(JSON.parse(m.data)));
  es.addEventListener("snapshot", (m) => paint(JSON.parse(m.data)));
  es.onerror = () => { $("#lseg").textContent = "Reconectando ao servidor…"; };
}
