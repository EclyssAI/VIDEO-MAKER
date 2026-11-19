"use strict";
/* Tokens de API para o ClipeiAki Live MCP (a chave aparece uma única vez; o servidor guarda só o hash). */
async function renderTokens(me) {
  const box = $("#tokens"); if (!box) return;
  const [{ tokens, scopes }, oc] = await Promise.all([api("/api/tokens"), api("/api/oauth/connections")]);
  const url = oc.mcp_url || `${me.public_url || location.origin}/mcp`;
  box.innerHTML = `<div class="row"><h2 id="tkh">Conectar ao seu Claude (MCP)</h2><span class="spacer"></span><span class="chip">${icon("key")}MCP</span></div>
    <p class="muted">O ClipeiAki não usa a API do Claude: quem analisa os momentos é o <strong>seu</strong> Claude, conectado pelo MCP. Ele vê os frames e a fala dos
      picos detectados, decide os cortes e acompanha o render. O uso conta no seu plano do Claude.</p>
    <ol class="steps compact"><li><b>1</b><span>No Claude (claude.ai ou Claude Desktop): Configurações → Conectores → Adicionar conector personalizado.</span></li>
      <li><b>2</b><span>Cole a URL <code>${esc(url)}</code> e conecte. Você volta aqui para autorizar.</span></li>
      <li><b>3</b><span>No chat, peça: “revise os momentos das minhas lives no ClipeiAki” (ou use o prompt <code>revisar_momentos</code>).</span></li></ol>
    <h3>Conexões ativas</h3><div class="stack">${oc.connections.length ? oc.connections.map((x) => `<div class="row tok"><div class="stack-tight"><strong>${esc(x.client_name)}</strong>
      <span class="muted small">${x.scopes.map(esc).join(" · ")} · conectado ${ago(x.created_at)}${x.last_used_at ? " · usado " + ago(x.last_used_at) : ""}</span></div>
      <span class="spacer"></span><button class="btn danger" data-oc="${esc(x.id)}">Desconectar</button></div>`).join("") : '<p class="muted">Nenhum Claude conectado.</p>'}</div>
    <h3>Token pessoal (Claude Code)</h3>
    <p class="muted">Para o Claude Code no terminal, você também pode criar um token e usar o header Authorization.</p>
    <form class="stack" id="tkf"><div class="field"><label for="tkn">Nome do token</label><input class="input" id="tkn" maxlength="60" placeholder="Ex.: Claude Code no notebook"></div>
      <fieldset class="scopes"><legend>Permissões</legend>${Object.entries(scopes).map(([k, v]) => `<label class="check"><input type="checkbox" value="${esc(k)}" ${k.endsWith(":read") ? "checked" : ""}><span><b>${esc(k)}</b> · ${esc(v)}</span></label>`).join("")}</fieldset>
      <div class="field"><label for="tkd">Validade</label><select class="input" id="tkd"><option value="30">30 dias</option><option value="90" selected>90 dias</option><option value="365">1 ano</option></select>
        <span class="hint">O token expira sozinho; revogue a qualquer momento. Limite: 120 leituras e 20 ações por minuto.</span></div>
      <div class="row"><button class="btn primary" type="submit">${icon("key")}Criar token</button></div></form>
    <div id="tknew"></div>
    <div class="stack">${tokens.length ? tokens.map((t) => `<div class="row tok"><div class="stack-tight"><strong>${esc(t.name)}</strong><span class="muted small">${t.scopes.map(esc).join(" · ")} · criado ${ago(t.created_at)}${t.last_used_at ? " · usado " + ago(t.last_used_at) : ""} · ${t.expires_at ? (t.expired ? "expirado" : "expira " + new Date(t.expires_at * 1000).toLocaleDateString("pt-BR")) : "sem expiração (antigo: recrie)"}</span></div>
      <span class="spacer"></span><button class="btn danger" data-rev="${esc(t.id)}">Revogar</button></div>`).join("") : '<p class="muted">Nenhum token ativo.</p>'}</div>`;
  $("#tkf").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const r = await api("/api/tokens", { method: "POST", json: { name: $("#tkn").value, days: +$("#tkd").value, scopes: $$("#tkf input[type=checkbox]:checked").map((x) => x.value) } });
      await renderTokens(me);
      $("#tknew").innerHTML = `<div class="notice stack"><strong>Copie agora — o token não será mostrado de novo.</strong><code class="tokv">${esc(r.token)}</code>
        <span class="muted small">Claude Code: <code>claude mcp add --transport http clipeiaki ${esc(url)} --header "Authorization: Bearer ${esc(r.token)}"</code></span>
        <div class="row"><button class="btn" id="tkcp">${icon("copy")}Copiar token</button></div></div>`;
      $("#tkcp").onclick = () => navigator.clipboard.writeText(r.token).then(() => toast("Token copiado."), () => toast("Não foi possível copiar.", true));
    } catch (err) { toast(err.message, true); }
  };
  $$("[data-oc]").forEach((b) => b.onclick = async () => {
    if (!confirm("Desconectar este Claude? Ele perde o acesso na hora.")) return;
    await api(`/api/oauth/connections/${b.dataset.oc}`, { method: "DELETE" }); renderTokens(me);
  });
  $$("[data-rev]").forEach((b) => b.onclick = async () => {
    if (!confirm("Revogar este token? Clientes que o usam perdem o acesso.")) return;
    await api(`/api/tokens/${b.dataset.rev}`, { method: "DELETE" }); renderTokens(me);
  });
}
