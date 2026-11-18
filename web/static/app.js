"use strict";
/* VIDEO-MAKER Web — SPA sem dependências. Todo dado do usuário passa por esc() antes de ir para o HTML. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const I = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  lib: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  check: '<path d="M20 6 9 17l-5-5"/>', download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>', trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  retry: '<path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5"/>', copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  out: '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>',
  back: '<path d="M15 18l-6-6 6-6"/>', undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
};
const icon = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[n]}</svg>`;
const S = { me: null, timer: null };
const LANG = { auto: "Detectar automaticamente", pt: "Português", en: "Inglês", es: "Espanhol" };
const PSTATUS = { uploading: ["Enviando", "run"], queued: ["Na fila", "run"], processing: ["Analisando", "run"], rendering: ["Renderizando", "run"], done: ["Pronto", "ok"], failed: ["Falhou", "bad"] };
const CSTATUS = { queued: ["Na fila", "run"], rendering: ["Renderizando", "run"], ready: ["Para revisar", "warn"], approved: ["Aprovado", "ok"], discarded: ["Descartado", ""], failed: ["Falhou", "bad"] };
const chip = (map, s) => { const [t, k] = map[s] || [s, ""]; return `<span class="chip ${k}">${esc(t)}</span>`; };
const fmtDur = (s) => { s = Math.round(s || 0); const m = Math.floor(s / 60); return m >= 60 ? `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}` : `${m}:${String(s % 60).padStart(2, "0")}`; };
const ago = (t) => { const d = Date.now() / 1000 - t; if (d < 60) return "agora"; if (d < 3600) return `há ${Math.floor(d / 60)} min`; if (d < 86400) return `há ${Math.floor(d / 3600)} h`; return new Date(t * 1000).toLocaleDateString("pt-BR"); };

function toast(msg, bad = false) {
  const d = document.createElement("div"); d.textContent = msg; if (bad) d.className = "bad";
  $("#toast").append(d); setTimeout(() => d.remove(), 4200);
}

async function api(path, { method = "GET", json, raw, quiet } = {}) {
  const opt = { method, headers: { "x-vm": "1" }, credentials: "same-origin" };
  if (json !== undefined) { opt.headers["content-type"] = "application/json"; opt.body = JSON.stringify(json); }
  const r = await fetch(path, opt);
  if (r.status === 401 && !quiet && !path.startsWith("/api/auth")) { S.me = null; go("/entrar"); throw new Error("Sessão expirada."); }
  const data = raw ? r : await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Algo deu errado. Tente de novo.");
  return data;
}

function go(path) { if (location.pathname !== path) history.pushState({}, "", path); route(); }
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]"); if (!a || e.metaKey || e.ctrlKey) return;
  e.preventDefault(); go(a.getAttribute("href"));
});
window.addEventListener("popstate", route);

/* ---------------- shell ---------------- */
function shell(active, content) {
  const me = S.me, L = me.limits;
  const nav = [["/", "home", "Painel"], ["/biblioteca", "lib", "Biblioteca"], ["/conta", "user", "Conta e plano"]];
  const planMini = L ? `<div class="plan-mini"><div class="row"><strong>${esc(me.plan_label)}</strong><span class="spacer"></span><span class="muted small">${me.usage.projects}/${L.projects_per_month}</span></div>
      <progress max="${L.projects_per_month}" value="${me.usage.projects}" aria-label="Projetos usados no mês"></progress>
      <span class="muted small">projetos neste mês</span></div>`
    : `<div class="plan-mini"><strong>Sem plano ativo</strong><a href="/conta" data-link class="small">Ver planos</a></div>`;
  return `<div class="shell"><aside class="side" aria-label="Navegação">
      <div class="brand"><img src="/static/icon.svg" alt="">VIDEO-MAKER</div>
      <nav class="nav"><a href="/novo" data-link class="cta">${icon("plus")}Novo projeto</a>
        ${nav.map(([h, i, t]) => `<a href="${h}" data-link ${active === h ? 'aria-current="page"' : ""}>${icon(i)}${t}</a>`).join("")}</nav>
      ${planMini}</aside>
    <main id="main" tabindex="-1">${content}</main>
    <nav class="tabbar" aria-label="Navegação">
      ${[["/", "home", "Painel"], ["/novo", "plus", "Novo"], ["/biblioteca", "lib", "Biblioteca"], ["/conta", "user", "Conta"]]
        .map(([h, i, t]) => `<a href="${h}" data-link ${active === h ? 'aria-current="page"' : ""}>${icon(i)}${t}</a>`).join("")}</nav></div>`;
}
function render(html) { $("#app").innerHTML = html; }
function poll(fn, ms = 3000) { clearTimeout(S.timer); S.timer = setTimeout(fn, ms); }

/* ---------------- rotas ---------------- */
async function route() {
  clearTimeout(S.timer);
  const p = location.pathname;
  if (!S.me) { try { S.me = await api("/api/me", { quiet: true }); } catch { S.me = null; } }
  if (!S.me) return p === "/criar-conta" ? authView("signup") : authView("login");
  if (p === "/entrar" || p === "/criar-conta") return go("/");
  try {
    if (p === "/") return await dashboard();
    if (p === "/novo") return newProject();
    if (p.startsWith("/projeto/")) return await studio(p.split("/")[2]);
    if (p === "/biblioteca") return await library();
    if (p === "/conta") return await account();
    render(shell("", `<div class="empty"><h2>Página não encontrada</h2><a class="btn" href="/" data-link>Voltar ao painel</a></div>`));
  } catch (e) { if (S.me) render(shell("", `<div class="empty"><h2>Não foi possível carregar</h2><p>${esc(e.message)}</p><a class="btn" href="/" data-link>Voltar</a></div>`)); }
}

function authView(mode) {
  render(`<div class="auth"><section class="auth-hero"><div class="brand"><img src="/static/icon.svg" alt="">VIDEO-MAKER <span class="muted">· Eclyss</span></div>
      <h1>Seus vídeos longos viram cortes prontos para postar.</h1>
      <p class="lead">Envie uma live, VOD ou gravação. Encontramos os momentos fortes, legendamos e montamos o vídeo vertical para TikTok, Reels e Shorts.</p>
      <ol class="steps"><li><b>1</b>Envie o vídeo</li><li><b>2</b>Revise os cortes sugeridos</li><li><b>3</b>Aprove e baixe em 1080×1920</li></ol></section>
    <section class="auth-panel"><form class="auth-box stack" id="authf" novalidate>
      <div class="seg" role="group" aria-label="Acesso"><button type="button" data-m="login" aria-pressed="${mode === "login"}">Entrar</button><button type="button" data-m="signup" aria-pressed="${mode === "signup"}">Criar conta</button></div>
      <h2>${mode === "login" ? "Bem-vindo de volta" : "Crie sua conta"}</h2>
      ${mode === "signup" ? `<div class="field"><label for="name">Nome</label><input class="input" id="name" autocomplete="name" maxlength="80"></div>` : ""}
      <div class="field"><label for="email">E-mail</label><input class="input" id="email" type="email" autocomplete="email" required></div>
      <div class="field"><label for="pw">Senha</label><input class="input" id="pw" type="password" autocomplete="${mode === "login" ? "current-password" : "new-password"}" minlength="8" required>
        ${mode === "signup" ? '<span class="hint">Mínimo de 8 caracteres.</span>' : ""}</div>
      ${mode === "signup" ? `<div class="field"><label for="invite">Código de convite <span class="muted">(se você recebeu um)</span></label><input class="input" id="invite" autocomplete="off"></div>` : ""}
      <p class="error-text" id="aerr" role="alert"></p>
      <button class="btn primary lg block" type="submit">${mode === "login" ? "Entrar" : "Criar conta"}</button>
    </form></section></div>`);
  $$(".seg button").forEach((b) => b.onclick = () => go(b.dataset.m === "login" ? "/entrar" : "/criar-conta"));
  $("#authf").onsubmit = async (e) => {
    e.preventDefault(); const btn = e.submitter; btn.disabled = true; $("#aerr").textContent = "";
    const body = { email: $("#email").value, password: $("#pw").value };
    if (mode === "signup") Object.assign(body, { name: $("#name").value, invite: $("#invite").value });
    try { S.me = await api(`/api/auth/${mode}`, { method: "POST", json: body }); go("/"); }
    catch (err) { $("#aerr").textContent = err.message; btn.disabled = false; }
  };
  $("#email").focus();
}

async function dashboard() {
  const [me, list] = await Promise.all([api("/api/me"), api("/api/projects")]); S.me = me; const L = me.limits;
  const first = (me.name || "").split(" ")[0];
  const meters = L ? `<div class="meters">
      <div class="meter"><span class="muted">Projetos no mês</span><div class="num">${me.usage.projects} <span>de ${L.projects_per_month}</span></div><progress max="${L.projects_per_month}" value="${me.usage.projects}"></progress></div>
      <div class="meter"><span class="muted">Minutos enviados</span><div class="num">${Math.round(me.usage.minutes)} <span>de ${L.minutes_per_month}</span></div><progress max="${L.minutes_per_month}" value="${me.usage.minutes}"></progress></div>
      <div class="meter"><span class="muted">Plano</span><div class="num">${esc(L.label)}</div><span class="muted small">até ${L.clips_per_project} cortes por vídeo · ${L.max_video_minutes} min por vídeo</span></div></div>`
    : `<div class="panel row"><div class="stack"><h2>Ative um plano para começar</h2><p class="muted">Escolha o Creator ou o Creator Studio para processar seus vídeos.</p></div><span class="spacer"></span><a class="btn primary" href="/conta" data-link>Ver planos</a></div>`;
  const rows = list.map((p) => {
    const run = ["queued", "processing", "rendering"].includes(p.status), n = Object.values(p.clips).reduce((a, b) => a + b, 0);
    const cover = p.cover_clip ? `<img class="cover" src="/api/clips/${esc(p.cover_clip)}/thumb" alt="" loading="lazy">` : `<div class="cover"></div>`;
    const sub = run && p.job ? `<span>${esc(p.job.stage || "Na fila")}</span>` : `<span>${n} ${n === 1 ? "corte" : "cortes"}</span>${p.clips.approved ? `<span>${p.clips.approved} aprovados</span>` : ""}`;
    return `<a class="proj" href="/projeto/${esc(p.id)}" data-link>${cover}<div class="meta"><h3>${esc(p.name)}</h3>
      <div class="sub">${sub}<span>${fmtDur(p.duration)}</span><span>${ago(p.created_at)}</span></div>
      ${run && p.status === "processing" && p.job ? `<progress max="100" value="${p.job.progress}" aria-label="Progresso"></progress>` : ""}</div>${chip(PSTATUS, p.status)}</a>`;
  }).join("");
  render(shell("/", `<div class="page-head"><div><h1>${first ? `Olá, ${esc(first)}` : "Seu painel"}</h1><p>Acompanhe seus projetos e revise os cortes prontos.</p></div>
      <a class="btn primary lg" href="/novo" data-link>${icon("plus")}Novo projeto</a></div>${meters}
    <h2 class="sr">Projetos</h2>
    ${list.length ? `<div class="projects">${rows}</div>` : `<div class="empty"><h2>Nenhum projeto ainda</h2><p>Envie uma live, VOD ou gravação e receba os melhores momentos em vídeo vertical, já legendados.</p><a class="btn primary lg" href="/novo" data-link>${icon("upload")}Enviar primeiro vídeo</a></div>`}`));
  if (list.some((p) => ["queued", "processing", "rendering"].includes(p.status))) poll(() => location.pathname === "/" && dashboard());
}

function newProject() {
  const L = S.me.limits;
  render(shell("/novo", `<div class="page-head"><div><h1>Novo projeto</h1><p>Envie o vídeo. A análise roda nos nossos servidores — pode fechar a aba depois do envio.</p></div></div>
    ${L ? "" : `<div class="panel row"><p>Sua conta não tem plano ativo.</p><span class="spacer"></span><a class="btn primary" href="/conta" data-link>Ver planos</a></div>`}
    <div class="new-grid"><form class="stack" id="nf">
      <label class="drop" id="drop" for="file">${icon("upload")}<strong id="fname">Arraste o vídeo aqui ou clique para escolher</strong>
        <span class="muted">MP4, MOV, MKV, WEBM ou TS · com áudio</span><input class="sr" type="file" id="file" accept="video/*,.mkv,.ts"></label>
      <div class="field"><label for="pname">Nome do projeto</label><input class="input" id="pname" maxlength="80" placeholder="Ex.: Live de sexta — GTA RP"></div>
      <div class="field"><label for="plang">Idioma da fala</label><select class="input" id="plang">${Object.entries(LANG).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        <span class="hint">As legendas saem em português. Falas em outro idioma são traduzidas quando a tradução automática está ativa.</span></div>
      <div id="up" class="stack" hidden><progress id="upbar" max="100" value="0" aria-label="Envio"></progress><span class="muted" id="uptxt">Enviando…</span></div>
      <p class="error-text" id="nerr" role="alert"></p>
      <button class="btn primary lg" type="submit" id="nsub" ${L ? "" : "disabled"}>${icon("upload")}Enviar e processar</button></form>
    <aside class="panel"><h3>Limites do seu plano</h3>${L ? `<ul class="limits">
      <li><span class="muted">Duração máxima</span><strong>${L.max_video_minutes} min</strong></li>
      <li><span class="muted">Tamanho máximo</span><strong>${L.max_upload_mb >= 1024 ? (L.max_upload_mb / 1024).toFixed(0) + " GB" : L.max_upload_mb + " MB"}</strong></li>
      <li><span class="muted">Cortes por vídeo</span><strong>até ${L.clips_per_project}</strong></li>
      <li><span class="muted">Projetos restantes no mês</span><strong>${Math.max(0, L.projects_per_month - S.me.usage.projects)}</strong></li>
      <li><span class="muted">Efeitos premium</span><strong>${L.premium_assets ? "Incluídos" : "Creator Studio"}</strong></li></ul>` : '<p class="muted">Sem plano ativo.</p>'}</aside></div>`));
  let file = null; const drop = $("#drop");
  const pick = (f) => { if (!f) return; file = f; $("#fname").textContent = f.name; if (!$("#pname").value) $("#pname").value = f.name.replace(/\.[^.]+$/, "").slice(0, 80); };
  $("#file").onchange = (e) => pick(e.target.files[0]);
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => pick(e.dataTransfer.files[0]));
  $("#nf").onsubmit = async (e) => {
    e.preventDefault(); $("#nerr").textContent = "";
    if (!file) { $("#nerr").textContent = "Escolha um vídeo para enviar."; return; }
    $("#nsub").disabled = true;
    try {
      const { id } = await api("/api/projects", { method: "POST", json: { name: $("#pname").value, filename: file.name, size: file.size, lang: $("#plang").value } });
      $("#up").hidden = false;
      await new Promise((ok, fail) => {
        const x = new XMLHttpRequest(); x.open("PUT", `/api/projects/${id}/source`); x.setRequestHeader("x-vm", "1");
        x.upload.onprogress = (ev) => { if (ev.lengthComputable) { const pc = Math.round(ev.loaded / ev.total * 100); $("#upbar").value = pc; $("#uptxt").textContent = pc < 100 ? `Enviando… ${pc}%` : "Verificando o vídeo…"; } };
        x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch {} x.status < 300 ? ok(d) : fail(new Error(d.detail || "Falha no envio.")); };
        x.onerror = () => fail(new Error("Conexão interrompida durante o envio.")); x.send(file);
      });
      S.me = await api("/api/me").catch(() => S.me); toast("Vídeo recebido. A análise começou."); go(`/projeto/${id}`);
    } catch (err) { $("#nerr").textContent = err.message; $("#nsub").disabled = false; $("#up").hidden = true; }
  };
}

async function studio(pid) {
  const p = await api(`/api/projects/${encodeURIComponent(pid)}`);
  const run = ["queued", "processing", "rendering"].includes(p.status);
  const head = `<div class="page-head"><div><a href="/" data-link class="back">${icon("back")}Painel</a><h1>${esc(p.name)}</h1>
      <p>${fmtDur(p.duration)} · ${esc(LANG[p.lang] || p.lang)} · ${esc(p.source_name || "")}</p></div>
      <div class="row">${chip(PSTATUS, p.status)}<button class="btn danger icon-btn" id="del" aria-label="Excluir projeto">${icon("trash")}</button></div></div>`;
  let status = "";
  if (p.status === "queued" || p.status === "processing") status = `<div class="panel studio-status"><div class="row"><strong>${esc(p.job?.stage || "Na fila de processamento")}</strong><span class="spacer"></span><span class="muted">${Math.round(p.job?.progress || 0)}%</span></div>
      <progress max="100" value="${p.job?.progress || 0}" aria-label="Progresso da análise"></progress><span class="muted">Detectando os momentos fortes e transcrevendo a fala. Você pode sair desta página.</span></div>`;
  if (p.status === "failed") status = `<div class="panel studio-status"><strong class="error-text">${esc(p.error || "O processamento falhou.")}</strong><div class="row"><button class="btn primary" id="retry">${icon("retry")}Reprocessar</button></div></div>`;
  if (p.status === "done" && !p.items.length) status = `<div class="empty"><h2>Nenhum momento encontrado</h2><p>Não achamos trechos com pico de áudio neste vídeo.</p></div>`;
  const cards = p.items.map(clipCard).join("");
  render(shell("", head + status + (p.items.length ? `<h2 class="sr">Cortes</h2><div class="clips">${cards}</div>` : "")));
  bindStudio(p);
  if (run || p.items.some((c) => ["queued", "rendering"].includes(c.status))) poll(() => location.pathname === `/projeto/${pid}` && refreshStudio(pid));
}

async function refreshStudio(pid) {
  if ($(".sheet")) return poll(() => refreshStudio(pid));  // não atrapalha quem está editando
  const playing = $$("video").some((v) => !v.paused); if (playing) return poll(() => refreshStudio(pid));
  await studio(pid);
}

function clipCard(c) {
  const cp = c.copy || {}; const busy = ["queued", "rendering"].includes(c.status);
  let media;
  if (c.has_video && !busy) media = `<video controls playsinline preload="none" poster="/api/clips/${esc(c.id)}/thumb?v=${Math.round(c.updated_at)}" src="/api/clips/${esc(c.id)}/video?v=${Math.round(c.updated_at)}"></video>`;
  else if (c.status === "failed") media = `<div class="state"><strong class="error-text">${esc(c.error || "Falha ao renderizar.")}</strong><button class="btn" data-act="retry" data-id="${esc(c.id)}">${icon("retry")}Tentar de novo</button></div>`;
  else media = `<div class="state"><div class="spinner" aria-hidden="true"></div><span>${busy ? esc(c.job?.stage || "Na fila de renderização") : "Aguardando"}</span></div>`;
  const acts = [];
  if (c.status === "ready") acts.push(`<button class="btn ok" data-act="approve" data-id="${esc(c.id)}">${icon("check")}Aprovar</button>`);
  if (c.status === "approved") acts.push(`<a class="btn primary" href="/api/clips/${esc(c.id)}/download" download>${icon("download")}Baixar MP4</a>`);
  if (["ready", "approved", "failed"].includes(c.status)) acts.push(`<button class="btn" data-act="edit" data-id="${esc(c.id)}">${icon("edit")}Editar</button>`);
  if (["ready", "approved"].includes(c.status)) acts.push(`<button class="btn ghost icon-btn" data-act="discard" data-id="${esc(c.id)}" aria-label="Descartar corte">${icon("trash")}</button>`);
  if (c.status === "discarded") acts.push(`<button class="btn" data-act="restore" data-id="${esc(c.id)}">${icon("undo")}Restaurar</button>`);
  return `<article class="clip ${esc(c.status)}"><div class="player">${chip(CSTATUS, c.status)}${media}</div>
    <h3>${esc(cp.screen_title || "Corte " + c.idx)}</h3>
    <p class="muted small">Corte ${c.idx} · ${c.duration}s${cp.source === "padrao" ? " · título padrão, edite à vontade" : ""}</p>
    <div class="row">${acts.join("")}</div></article>`;
}

function bindStudio(p) {
  $("#del")?.addEventListener("click", async () => {
    if (!confirm(`Excluir o projeto "${p.name}" e todos os cortes? Isso não pode ser desfeito.`)) return;
    try { await api(`/api/projects/${p.id}`, { method: "DELETE" }); toast("Projeto excluído."); go("/"); } catch (e) { toast(e.message, true); }
  });
  $("#retry")?.addEventListener("click", async () => { try { await api(`/api/projects/${p.id}/retry`, { method: "POST" }); studio(p.id); } catch (e) { toast(e.message, true); } });
  $$("[data-act]").forEach((b) => b.addEventListener("click", async () => {
    const id = b.dataset.id, act = b.dataset.act, c = p.items.find((x) => x.id === id);
    if (act === "edit") return editor(c, p.id);
    b.disabled = true;
    try { await api(`/api/clips/${id}/${act}`, { method: "POST" }); if (act === "approve") toast("Corte aprovado. Já pode baixar."); studio(p.id); }
    catch (e) { toast(e.message, true); b.disabled = false; }
  }));
}

function editor(c, pid) {
  const cp = c.copy || {}; const caps = cp.captions || [];
  const wrap = document.createElement("div");
  wrap.innerHTML = `<div class="scrim" data-close></div><section class="sheet" role="dialog" aria-modal="true" aria-labelledby="edt">
    <header><h2 id="edt">Editar corte ${c.idx}</h2><span class="spacer"></span><button class="btn ghost icon-btn" data-close aria-label="Fechar">${icon("x")}</button></header>
    <form class="body" id="ef">
      <div class="field"><label for="e1">Título na tela</label><input class="input" id="e1" maxlength="40" value="${esc(cp.screen_title)}"><span class="hint">Aparece no topo do vídeo. Curto e em maiúsculas funciona melhor.</span></div>
      <div class="field"><label for="e2">Título do post</label><input class="input" id="e2" maxlength="100" value="${esc(cp.title)}"></div>
      <div class="field"><label for="e3">Descrição</label><textarea class="input" id="e3" maxlength="2000">${esc(cp.description)}</textarea></div>
      <div class="field"><label for="e4">Hashtags</label><input class="input" id="e4" value="${esc((cp.hashtags || []).join(" "))}"></div>
      ${caps.length ? `<div class="field"><span class="label"><strong>Legendas</strong></span><div class="caps">${caps.map((k, i) => `<div class="cap"><span>${k.s.toFixed(1)}s</span><input class="input" data-cap="${i}" maxlength="80" value="${esc(k.t)}" aria-label="Legenda em ${k.s.toFixed(1)} segundos"></div>`).join("")}</div><span class="hint">Apague o texto de um bloco para removê-lo.</span></div>` : ""}
      <button class="btn ghost" type="button" id="cpy">${icon("copy")}Copiar título, descrição e hashtags</button>
    </form>
    <footer><button class="btn ghost" data-close>Cancelar</button><span class="spacer"></span><button class="btn primary" id="esave">Salvar e renderizar</button></footer></section>`;
  document.body.append(wrap); const prev = document.activeElement; $("#e1").focus();
  const close = () => { wrap.remove(); prev?.focus?.(); };
  $$("[data-close]", wrap).forEach((x) => x.addEventListener("click", close));
  wrap.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  $("#cpy").onclick = async () => { try { await navigator.clipboard.writeText(`${$("#e2").value}\n\n${$("#e3").value}\n\n${$("#e4").value}`); toast("Texto copiado."); } catch { toast("Não foi possível copiar.", true); } };
  $("#esave").onclick = async () => {
    $("#esave").disabled = true;
    const body = { screen_title: $("#e1").value, title: $("#e2").value, description: $("#e3").value, hashtags: $("#e4").value };
    if (caps.length) body.captions = $$("[data-cap]", wrap).map((x) => x.value);
    try { await api(`/api/clips/${c.id}`, { method: "PATCH", json: body }); close(); toast("Salvo. Renderizando a nova versão…"); studio(pid); }
    catch (e) { toast(e.message, true); $("#esave").disabled = false; }
  };
}

async function library() {
  const items = await api("/api/library");
  const cards = items.map((c) => `<article class="clip"><div class="player"><video controls playsinline preload="none" poster="/api/clips/${esc(c.id)}/thumb?v=${Math.round(c.updated_at)}" src="/api/clips/${esc(c.id)}/video?v=${Math.round(c.updated_at)}"></video></div>
      <h3>${esc(c.copy.screen_title)}</h3><p class="muted small">${esc(c.project_name)} · ${c.duration}s</p>
      <div class="row"><a class="btn primary" href="/api/clips/${esc(c.id)}/download" download>${icon("download")}Baixar</a>
      <button class="btn" data-copy="${esc(c.id)}">${icon("copy")}Copiar texto</button></div></article>`).join("");
  render(shell("/biblioteca", `<div class="page-head"><div><h1>Biblioteca</h1><p>Cortes aprovados, prontos para postar.</p></div></div>
    ${items.length ? `<div class="clips">${cards}</div>` : `<div class="empty"><h2>Nada aprovado ainda</h2><p>Revise os cortes de um projeto e aprove os que quiser publicar. Eles aparecem aqui para baixar.</p><a class="btn" href="/" data-link>Ir para o painel</a></div>`}`));
  $$("[data-copy]").forEach((b) => b.onclick = async () => {
    try { const r = await api(`/api/clips/${b.dataset.copy}/caption.txt`, { raw: true }); await navigator.clipboard.writeText(await r.text()); toast("Título, descrição e hashtags copiados."); }
    catch { toast("Não foi possível copiar.", true); }
  });
}

async function account() {
  const b = await api("/api/billing"); const me = b.me; S.me = me;
  const feat = (L) => [`${L.projects_per_month} projetos por mês`, `${L.minutes_per_month} minutos de vídeo por mês`, `Vídeos de até ${L.max_video_minutes} min`, `Até ${L.clips_per_project} cortes por vídeo`, "Legendas, enquadramento de webcam e 1080×1920",
    ...(L.premium_assets ? ["Efeitos premium: SFX e zoom no momento forte"] : [])];
  const planCard = (k, L) => {
    const cur = me.plan === k, url = b.checkout[k];
    const cta = cur ? `<span class="chip ok">Seu plano</span>` : url ? `<a class="btn ${k === "studio" ? "primary" : ""} block" href="${esc(url)}" target="_blank" rel="noopener">${me.plan && me.plan !== "beta" ? "Mudar para este plano" : "Assinar"}</a>`
      : `<span class="muted">Assinaturas abrem em breve.</span>`;
    return `<div class="plan ${k === "studio" ? "featured" : ""}"><h3>${esc(L.label)}</h3><div class="price">R$ ${L.price_brl.toFixed(2).replace(".", ",")} <span>/mês</span></div>
      <ul>${feat(L).map((f) => `<li>${icon("check")}<span>${esc(f)}</span></li>`).join("")}</ul>${cta}</div>`;
  };
  const statusTxt = { active: "Ativa", past_due: "Pagamento pendente", canceled: "Cancelada — acesso até o fim do período", revoked: "Encerrada", none: "" }[me.plan_status] || "";
  render(shell("/conta", `<div class="page-head"><div><h1>Conta e plano</h1><p>${esc(me.email)}</p></div><button class="btn ghost" id="logout">${icon("out")}Sair</button></div>
    <div class="settings-grid"><form class="panel stack" id="pf"><h2>Perfil</h2>
      <div class="field"><label for="n">Nome</label><input class="input" id="n" maxlength="80" value="${esc(me.name)}"></div>
      <div class="field"><label for="h">@ do seu canal</label><input class="input" id="h" maxlength="30" value="${esc(me.handle)}" placeholder="@seucanal"><span class="hint">Aparece no rodapé de cada corte. Vale para os próximos renders.</span></div>
      <div class="row"><button class="btn primary" type="submit">Salvar perfil</button></div></form>
    <div class="panel stack"><h2>Plano atual</h2>${me.limits ? `<div class="row"><strong class="num">${esc(me.plan_label)}</strong>${statusTxt ? `<span class="chip ${me.plan_status === "active" ? "ok" : "warn"}">${esc(statusTxt)}</span>` : ""}</div>
      ${me.plan_until > 0 && me.plan !== "beta" ? `<p class="muted">Válido até ${new Date(me.plan_until * 1000).toLocaleDateString("pt-BR")}</p>` : ""}
      <p class="muted">${me.usage.projects} de ${me.limits.projects_per_month} projetos e ${Math.round(me.usage.minutes)} de ${me.limits.minutes_per_month} minutos usados neste mês.</p>` : `<p class="muted">Nenhum plano ativo.</p>`}
      ${me.claude_copy ? "" : `<p class="muted small">Tradução e títulos automáticos estão desativados neste ambiente: os cortes saem com título padrão editável e legenda no idioma original.</p>`}</div></div>
    <h2 class="section-title">Planos</h2><div class="plans">${Object.entries(b.plans).map(([k, L]) => planCard(k, L)).join("")}</div>`));
  $("#pf").onsubmit = async (e) => { e.preventDefault(); try { S.me = await api("/api/me", { method: "PATCH", json: { name: $("#n").value, handle: $("#h").value } }); $("#h").value = S.me.handle; toast("Perfil salvo."); } catch (err) { toast(err.message, true); } };
  $("#logout").onclick = async () => { await api("/api/auth/logout", { method: "POST" }).catch(() => {}); S.me = null; go("/entrar"); };
}

route();
