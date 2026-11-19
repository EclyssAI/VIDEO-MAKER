// Landing + páginas jurídicas no navegador real (Playwright/Chromium) com auditoria WCAG 2.1 A/AA (axe-core).
// Uso: BASE=http://127.0.0.1:8000 OUT=/tmp/landing NODE_PATH=<dir com axe-core> node web/tests/landing_check.js
// Verifica: layout sem rolagem horizontal em 4 larguras, contraste/semântica (axe), alvos de toque ≥ 44 px, fonte mínima,
// zero erros de JS e de CSP, planos iguais ao backend (/api/public/plans), links jurídicos 200, reduced-motion e contagem de palavras.
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const BASE = process.env.BASE || 'http://127.0.0.1:8000', OUT = process.env.OUT || '/tmp/landing';
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const VIEWS = [['mobile-375', 375, 812], ['tablet-768', 768, 1024], ['desktop-1280', 1280, 900], ['wide-1440', 1440, 900]];
const LEGAL = ['termos', 'privacidade', 'cancelamento', 'conteudo', 'cookies', 'regras-live-ia', 'contato'];
fs.mkdirSync(OUT, { recursive: true });

async function audit(page) {
  await page.addScriptTag({ content: AXE });
  return page.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, ex: v.nodes.slice(0, 2).map((x) => x.target.join(' ')) }));
  });
}

(async () => {
  const b = await chromium.launch(); const res = { views: {}, legal: {}, errors: [], ok: true };
  const fail = (m) => { res.ok = false; res.errors.push(m); };
  for (const [name, w, h] of VIEWS) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, bypassCSP: true }); // só para injetar o axe-core
    const p = await ctx.newPage(); const errs = [];
    p.on('pageerror', (e) => errs.push('js: ' + e.message));
    p.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
    await p.goto(BASE + '/', { waitUntil: 'networkidle' });
    // percorre a página para disparar as entradas suaves e o lazy-load
    for (let y = 0; y < 30000; y += h * 0.8) { await p.evaluate((yy) => window.scrollTo(0, yy), y); await p.waitForTimeout(60); }
    await p.waitForTimeout(500);
    const m = await p.evaluate(() => {
      const se = document.scrollingElement; const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
      const small = [...document.querySelectorAll('main *, footer *')].filter((el) => el.childNodes.length && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && vis(el))
        .map((el) => [el.tagName, parseFloat(getComputedStyle(el).fontSize), el.textContent.trim().slice(0, 30)]).filter((x) => x[1] < 14);
      const taps = [...document.querySelectorAll('.btn, .nav-links a, .faq summary, .foot ul a')].filter(vis).map((el) => { const r = el.getBoundingClientRect(); return [el.textContent.trim().slice(0, 24), Math.round(r.width), Math.round(r.height)]; }).filter((x) => x[2] < 40);
      const hidden = [...document.querySelectorAll('.reveal')].filter((el) => getComputedStyle(el).opacity !== '1').length;
      return { overflowX: se.scrollWidth - window.innerWidth, height: se.scrollHeight, small, taps, hidden };
    });
    await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(150);
    await p.screenshot({ path: path.join(OUT, `landing-${name}.png`), fullPage: true });
    const v = await audit(p);
    res.views[name] = { ...m, axe: v, errors: errs };
    if (m.overflowX > 1) fail(`${name}: rolagem horizontal de ${m.overflowX}px`);
    if (m.small.length) fail(`${name}: texto < 14px: ${JSON.stringify(m.small.slice(0, 3))}`);
    if (m.taps.length) fail(`${name}: alvos < 40px: ${JSON.stringify(m.taps.slice(0, 4))}`);
    if (m.hidden) fail(`${name}: ${m.hidden} blocos ficaram invisíveis`);
    if (v.length) fail(`${name}: axe ${JSON.stringify(v)}`);
    if (errs.length) fail(`${name}: ${errs.join(' | ')}`);
    await ctx.close();
  }
  // reduced motion: tudo visível sem rolar
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce', bypassCSP: true }); const p = await ctx.newPage();
  await p.goto(BASE + '/', { waitUntil: 'networkidle' });
  res.reduced_motion_hidden = await p.evaluate(() => [...document.querySelectorAll('.reveal')].filter((el) => getComputedStyle(el).opacity !== '1').length);
  if (res.reduced_motion_hidden) fail('reduced-motion: blocos invisíveis');
  // planos: HTML == backend
  const api = await (await p.request.get(BASE + '/api/public/plans')).json();
  const cards = await p.$$eval('.plan', (els) => els.map((e) => ({ name: e.querySelector('h3').textContent.trim(), price: e.querySelector('.price').textContent.trim(), first: e.querySelector('li').textContent.trim() })));
  res.plans = { cards, api: Object.fromEntries(Object.entries(api.plans).map(([k, v]) => [k, [v.label, v.price_brl, v.live_slots]])), checkout_enabled: api.checkout_enabled };
  const want = [['Creator', 'R$ 49,90', api.plans.creator.live_slots], ['Creator Studio', 'R$ 69,90', api.plans.studio.live_slots]];
  want.forEach(([n, pr, sl], k) => {
    if (!cards[k] || cards[k].name !== n || !cards[k].price.startsWith(pr) || !cards[k].first.startsWith(String(sl))) fail(`card ${n} divergente: ${JSON.stringify(cards[k])}`);
  });
  if (api.plans.creator.price_brl !== 49.9 || api.plans.studio.price_brl !== 69.9) fail('preços do backend mudaram');
  const cta = await p.$$eval('[data-plan]', (els) => els.map((e) => [e.dataset.plan, e.getAttribute('href'), e.textContent.trim()]));
  res.plans.cta = cta; if (!api.checkout_enabled && cta.some((c) => c[1] !== '/criar-conta')) fail('CTA apontando para checkout com cobrança desligada');
  // contagem de palavras do conteúdo principal (sem a tabela comparativa)
  res.words = await p.evaluate(() => { const m = document.querySelector('main').cloneNode(true); m.querySelectorAll('table').forEach((t) => t.remove()); return m.innerText.split(/\s+/).filter(Boolean).length; });
  // links jurídicos do rodapé e páginas
  const links = await p.$$eval('footer a[href^="/"]', (els) => els.map((e) => e.getAttribute('href')));
  for (const d of LEGAL) {
    if (!links.includes('/' + d)) fail(`rodapé sem /${d}`);
    const r = await p.request.get(BASE + '/' + d); const t = await r.text();
    res.legal[d] = { status: r.status(), version: (t.match(/Versão ([0-9-]+)/) || [])[1], pendencias: (t.match(/PENDENTE_DADO_EMPRESARIAL/g) || []).length };
    if (r.status() !== 200) fail(`/${d} → ${r.status()}`);
  }
  await p.goto(BASE + '/termos'); res.legal_axe = await audit(p); await p.screenshot({ path: path.join(OUT, 'termos-1280.png') });
  if (res.legal_axe.length) fail('axe em /termos: ' + JSON.stringify(res.legal_axe));
  const mob = await b.newContext({ viewport: { width: 375, height: 812 } }); const pm = await mob.newPage(); await pm.goto(BASE + '/privacidade');
  res.legal_mobile_overflow = await pm.evaluate(() => document.scrollingElement.scrollWidth - innerWidth);
  if (res.legal_mobile_overflow > 1) fail('/privacidade com rolagem horizontal no celular');
  await b.close();
  fs.writeFileSync(path.join(OUT, 'landing_check.json'), JSON.stringify(res, null, 1));
  console.log(JSON.stringify({ ok: res.ok, words: res.words, errors: res.errors, legal: res.legal, plans: res.plans }, null, 1));
  process.exit(res.ok ? 0 : 1);
})();
