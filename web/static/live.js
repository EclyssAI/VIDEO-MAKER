"use strict";
/* Claude Live Monitor — tudo aqui vem do backend (REST + SSE). Nada é simulado no navegador. */
const LSTATUS = { starting: ["Iniciando", "run"], running: ["Gravando", "ok"], reconnecting: ["Reconectando", "warn"], stopping: ["Encerrando", "warn"], stopped: ["Encerrada", ""] };
const STOPR = { user: "parada por você", duration: "limite de duração", budget: "orçamento esgotado", calls: "limite de chamadas", offline: "live offline", error: "erro no agente",
  quota: "franquia mensal esgotada", plan: "plano inativo" };
const CLAUDE = { disabled: ["Revisão pelo seu Claude (MCP)", ""], idle: ["Pronto, aguardando momento", "warn"], calling: ["Analisando agora", "run"], ok: ["Conectado", "ok"], error: ["Erro na API", "bad"] };
const MSTATUS = { waiting: "Gravando o pós-evento", ready: "Na fila do Claude", analyzing: "Claude analisando", candidate: "Candidato (sem análise)", rejected: "Claude descartou",
  clip_pending: "Claude aprovou · cortando", clip_requested: "Corte solicitado", clip_queued: "Renderizando", clipped: "Corte pronto", clip_failed: "Falha no corte",
  skipped: "Não analisado", invalid: "Resposta inválida", expired: "Expirado" };
const fmtT = (t) => { t = Math.max(0, Math.round(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0"); };
const clock = (w) => w ? new Date(w * 1000).toLocaleTimeString("pt-BR") : "—";
const usd = (v) => "US$ " + (v || 0).toFixed(v < 0.1 ? 4 : 2);

function claudeChip(cl) { const [t, k] = CLAUDE[cl.state] || [cl.state, ""]; return `<span class="chip ${k}">Claude: ${esc(t)}</span>`; }

function liveDashCard(sessions, me) {
  const act = sessions.filter((s) => s.status !== "stopped"); const cs = me.live_claude || {}; const slots = me.limits ? me.limits.live_slots : 0;
  const claude = `<a class="chip" href="/conta#tokens" data-link>Revisão pelo seu Claude (MCP)</a>`;
  const body = `<div class="row"><p class="muted">${act.length ? `${act.length} de ${slots} transmissões sendo monitoradas agora.` : `Conecte até ${slots} transmissão(ões) da Twitch e acompanhe todas numa grade, com preview real de cada uma.`}</p>
      <span class="spacer"></span><a class="btn primary" href="/live" data-link>${icon("radio")}Abrir Live Monitor</a></div>`;
  return `<section class="panel live-dash stack" aria-labelledby="ldh"><div class="row"><h2 id="ldh">Live Monitor</h2><span class="spacer"></span>${claude}</div>
    ${body}</section>`;
}

/* estado da transmissão (vem do backend: service.stream_out) */
const SSTATE = { live: ["Ao vivo · gravando", "ok"], starting: ["Iniciando", "run"], reconnecting: ["Reconectando", "warn"], stopping: ["Encerrando", "warn"],
  offline: ["Offline", ""], error: ["Erro", "bad"], paused: ["Pausado", ""], limit: ["Limite atingido", "warn"], idle: ["Conectado · parado", ""] };
const ACTIVE_ST = ["live", "starting", "reconnecting", "stopping"];
const LCFG = () => { try { return JSON.parse(localStorage.getItem("lcfg") || "{}"); } catch { return {}; } };

function streamCard(x, testSource) {
  const [st, k] = SSTATE[x.state] || [x.state, ""]; const s = x.session; const active = ACTIVE_ST.includes(x.state);
  const plat = testSource ? "Fonte de teste (arquivo local)" : "Twitch";
  const pv = s && s.preview ? `<img src="${esc(s.preview.url)}" alt="Último frame gravado de ${esc(x.channel)}, t=${fmtT(s.preview.t_stream)}" loading="lazy">
      <span class="pv-meta">frame gravado · t=${fmtT(s.preview.t_stream)} · ${clock(s.preview.wall_at)}</span>`
    : `<div class="pv-empty">${active ? "Aguardando o primeiro bloco gravado…" : "Sem preview: a transmissão não está sendo gravada"}</div>`;
  const stats = s ? `<dl class="sstats"><div><dt>Monitorando</dt><dd>${fmtT(s.monitoring_s)}</dd></div><div><dt>Gravado</dt><dd>${fmtT(s.recorded_s)}</dd></div>
      <div><dt>Candidatos</dt><dd>${s.candidates}</dd></div><div><dt>Cortes</dt><dd>${s.clips}</dd></div></dl>` : `<p class="muted small">Ainda não monitorada.</p>`;
  const why = s && !active && s.stop_reason ? `<p class="muted small">Última sessão: ${esc(STOPR[s.stop_reason] || s.stop_reason)}${s.error ? " · " + esc(s.error) : ""}</p>` : "";
  return `<article class="scard st-${esc(x.state)}" aria-label="Transmissão ${esc(x.channel)}">
    <div class="pv">${pv}<span class="chip ${k}">${esc(st)}</span></div>
    <div class="scard-b"><div class="row"><h3 title="${esc(x.channel)}">${esc(x.channel)}</h3><span class="spacer"></span><span class="plat">${esc(plat)} · slot ${x.slot}</span></div>
      ${stats}${why}
      <div class="row sacts">${active ? `<button class="btn" data-sact="pause" data-id="${esc(x.id)}" ${x.state === "stopping" ? "disabled" : ""}>${icon("stop")}Pausar</button>`
        : `<button class="btn primary" data-sact="start" data-id="${esc(x.id)}">${icon("play")}Iniciar</button>`}
        ${s ? `<a class="btn" href="/live/${esc(s.id)}" data-link>${icon("radio")}Inspecionar</a>` : ""}
        <button class="btn ghost icon-btn" data-sact="remove" data-id="${esc(x.id)}" aria-label="Remover ${esc(x.channel)}" title="Remover">${icon("trash")}</button></div></div></article>`;
}

async function liveHome() {
  const [mon, sessions, me] = await Promise.all([api("/api/live/monitor"), api("/api/live/sessions"), api("/api/me")]); S.me = me; const L = me.limits; const cs = mon.claude || {};
  const cfg = LCFG(); const free = mon.slots - mon.streams.length;
  const past = sessions.filter((s) => s.status === "stopped").slice(0, 12).map((s) => `<a class="proj" href="/live/${esc(s.id)}" data-link><div class="cover live-cover">${icon("radio")}</div><div class="meta"><h3>twitch.tv/${esc(s.channel)}</h3>
    <div class="sub"><span>${fmtT(s.recorded_s)} gravados</span><span>${s.calls} análises</span><span>${usd(s.spent_usd)}</span><span>${ago(s.created_at)}</span></div></div>
    <span class="chip">${esc(STOPR[s.stop_reason] || LSTATUS[s.status][0])}</span></a>`).join("");
  const q = mon.quota;
  render(shell("/live", `<div class="page-head"><div><h1>Live Monitor</h1><p>${mon.slots ? `Plano ${esc(mon.plan)}: até <strong>${mon.slots}</strong> transmissões ao mesmo tempo.` : "Sem plano ativo."}
      O agente do servidor grava cada transmissão em blocos de 10 s; nada depende desta aba aberta.</p></div>
      <div class="row">${mon.mcp_last_use && Date.now() / 1000 - mon.mcp_last_use < 3600 ? `<span class="chip ok">Seu Claude conectado · ${ago(mon.mcp_last_use)}</span>` : `<a class="chip" href="/conta#tokens" data-link>Conectar seu Claude (MCP)</a>`}</div></div>
    <div class="meters"><div class="meter"><span class="muted">Monitorando agora</span><div class="num">${mon.active} <span>de ${mon.slots}</span></div><progress max="${mon.slots || 1}" value="${mon.active}" aria-label="Transmissões ativas"></progress></div>
      ${q ? `<div class="meter"><span class="muted">Horas de monitoramento no mês</span><div class="num">${mon.usage.live_hours.toFixed(1)} <span>de ${q.live_hours_per_month} h</span></div><progress max="${q.live_hours_per_month}" value="${mon.usage.live_hours}" aria-label="Horas usadas"></progress></div>
      <div class="meter"><span class="muted">Cortes do Live no mês</span><div class="num">${mon.usage.live_clips} <span>de ${q.live_clips_per_month}</span></div><progress max="${q.live_clips_per_month}" value="${mon.usage.live_clips}" aria-label="Cortes usados"></progress></div>` : ""}</div>
    <p class="muted small">Gravação e detecção rodam no servidor. A decisão dos cortes é sua ou do seu Claude, conectado pelo MCP.</p>
    ${mon.test_source ? `<p class="notice bad">Ambiente de teste: as transmissões abaixo são arquivos de vídeo locais tocados como se fossem lives (não são canais reais).</p>` : ""}
    ${free > 0 && L ? `<form class="panel stack connect" id="lf" aria-labelledby="lfh"><h2 id="lfh">Conectar transmissão <span class="muted small">(${free} slot${free > 1 ? "s" : ""} livre${free > 1 ? "s" : ""})</span></h2>
      <div class="field"><label for="lch">Canal da Twitch</label><div class="row"><input class="input grow" id="lch" placeholder="twitch.tv/canal" autocomplete="off" required>
        <button class="btn" type="button" id="lck">Verificar se está ao vivo</button></div><span class="hint" id="lst" aria-live="polite"></span></div>
      <fieldset class="scopes"><legend>Declaração obrigatória</legend>
        <label class="check"><input type="radio" name="rb" value="owner" required> Sou o titular deste canal</label>
        <label class="check"><input type="radio" name="rb" value="authorized"> Tenho autorização do titular para gerar cortes deste canal</label>
        <span class="hint">Leia as <a href="/regras-live-ia" target="_blank" rel="noopener">Regras do Live Monitor</a>. Monitorar canais de terceiros sem autorização é proibido.</span></fieldset>
      <p class="error-text" id="lerr" role="alert"></p><div class="row"><button class="btn primary" id="lgo" type="submit">${icon("plus")}Conectar</button></div></form>` : ""}
    <details class="panel lcfg"><summary>Configuração das próximas sessões</summary><div class="two">
      <div class="field"><label for="lbud">Orçamento de IA por sessão (US$)</label><input class="input" id="lbud" type="number" min="0" step="0.05" max="${L ? L.live_budget_usd_max : 0}" value="${cfg.budget ?? (L ? Math.min(0.5, L.live_budget_usd_max) : 0)}">
        <span class="hint">Máximo do plano: US$ ${L ? L.live_budget_usd_max.toFixed(2) : "0"} por sessão.</span></div>
      <div class="field"><label for="lmin">Duração máxima por sessão (min)</label><input class="input" id="lmin" type="number" min="1" max="${L ? L.live_max_minutes : 0}" value="${cfg.minutes ?? (L ? Math.min(60, L.live_max_minutes) : 0)}">
        <span class="hint">Até ${L ? L.live_max_minutes : 0} min no seu plano.</span></div>
      <div class="field"><label for="llang">Idioma das lives</label><select class="input" id="llang">${Object.entries(LANG).map(([k, v]) => `<option value="${k}" ${cfg.lang === k ? "selected" : ""}>${v}</option>`).join("")}</select></div></div></details>
    <h2 class="section-title">Transmissões <span class="muted small">${mon.streams.length} de ${mon.slots} slots</span></h2>
    <div class="sgrid" id="sgrid" data-slots="${mon.slots}"></div>
    ${past ? `<h2 class="section-title">Histórico de sessões</h2><div class="projects">${past}</div>` : ""}`));
  const paintGrid = (m) => {
    const cards = m.streams.map((x) => streamCard(x, m.test_source)); for (let k = m.streams.length; k < m.slots; k++) cards.push(`<div class="scard empty-slot" aria-label="Slot livre"><span>Slot ${k + 1} livre</span></div>`);
    $("#sgrid").innerHTML = cards.join("") || `<p class="muted">Sem plano ativo.</p>`;
  };
  paintGrid(mon);
  const saveCfg = () => localStorage.setItem("lcfg", JSON.stringify({ budget: +$("#lbud").value, minutes: +$("#lmin").value, lang: $("#llang").value }));
  ["#lbud", "#lmin", "#llang"].forEach((s) => $(s)?.addEventListener("change", saveCfg));
  $("#sgrid").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-sact]"); if (!b) return; const id = b.dataset.id, act = b.dataset.sact;
    if (act === "remove" && !confirm("Remover esta transmissão? Se estiver gravando, o monitoramento para. Os cortes já gerados continuam na Biblioteca.")) return;
    b.disabled = true;
    try {
      if (act === "start") await api(`/api/live/streams/${id}/start`, { method: "POST", json: { budget_usd: +$("#lbud").value, max_minutes: +$("#lmin").value, lang: $("#llang").value } });
      else if (act === "pause") await api(`/api/live/streams/${id}/pause`, { method: "POST" });
      else { await api(`/api/live/streams/${id}`, { method: "DELETE" }); return liveHome(); }
      paintGrid(await api("/api/live/monitor"));
    } catch (err) { toast(err.message, true); b.disabled = false; }
  });
  const chk = async () => {
    $("#lst").textContent = "Consultando a Twitch…";
    try { const r = await api(`/api/live/channel?q=${encodeURIComponent($("#lch").value)}`); $("#lst").textContent = r.live ? `Ao vivo: ${r.title || ""} · ${r.category || ""}` : (r.error || "Este canal não está ao vivo agora."); return r; }
    catch (e) { $("#lst").textContent = e.message; return null; }
  };
  $("#lck")?.addEventListener("click", chk);
  $("#lf")?.addEventListener("submit", async (e) => {
    e.preventDefault(); $("#lerr").textContent = ""; $("#lgo").disabled = true;
    try { await api("/api/live/streams", { method: "POST", json: { channel: $("#lch").value, rights_basis: ($("input[name=rb]:checked") || {}).value } }); toast("Transmissão conectada."); liveHome(); }
    catch (err) { $("#lerr").textContent = err.message; $("#lgo").disabled = false; }
  });
  const tick = async () => { if (location.pathname !== "/live") return; try { paintGrid(await api("/api/live/monitor")); } catch { /* rede */ } poll(tick, 4000); };
  poll(tick, 4000);
}

const KIND = {
  created: (d) => `Sessão criada · orçamento ${usd(d.budget_usd)} · até ${d.max_minutes} min`,
  started: () => "Agente iniciou a gravação", resumed: () => "Sessão retomada por outro agente após falha",
  layout: (d) => d.webcam ? "Webcam detectada no canto da tela" : "Sem webcam: enquadramento de tela cheia",
  candidate: (d) => `Momento candidato · áudio ${d.audio_db_above_baseline > 0 ? "+" : ""}${d.audio_db_above_baseline} dB${d.keywords.length ? " · “" + d.keywords.join("”, “") + "”" : ""}${d.visual_change_z >= 6 ? " · mudança de imagem" : ""}`,
  analysis_started: (d) => `Enviado ao Claude: ${d.frames_t.length} frame(s) em t=${d.frames_t.map(fmtT).join(", ")} + transcrição`,
  analysis: (d) => `${d.via === "mcp" ? "Seu Claude (MCP" + (d.client ? " · " + d.client : "") + ")" : "Claude"}: ${d.decision === "clip" ? "CORTAR" : "IGNORAR"} (${Math.round(d.confidence * 100)}%) · ${d.reason}`,
  frames_shared: (d) => `${d.frames.length} frame(s) mostrados ao seu Claude pelo MCP (t=${d.frames.map((f) => fmtT(f.t)).join(", ")})`,
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
      ${cl.state === "disabled" ? `<p class="notice">${esc(cl.detail)} Os momentos ficam como candidatos até o seu Claude (pelo MCP) ou você decidir.</p>` : `<p class="muted small">${esc(cl.detail || "")}${cl.last_call_at ? " · última chamada " + clock(cl.last_call_at) : ""}</p>`}
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
