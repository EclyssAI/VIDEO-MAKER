// Fotografa telas reais do app para a landing (chamado por capture_demo.py). Converte para WebP com o próprio Chromium.
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const { BASE, COOKIE, PID, OUT, MCP } = process.env; const SHOT = process.env.SHOT || 'monitor.webp';
async function webp(page, file, clip) {
  const png = await page.screenshot(clip ? { clip } : {});
  const b64 = png.toString('base64');
  const data = await page.evaluate(async (src) => { const img = new Image(); img.src = 'data:image/png;base64,' + src; await img.decode();
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; c.getContext('2d').drawImage(img, 0, 0);
    return c.toDataURL('image/webp', 0.82).split(',')[1]; }, b64);
  fs.writeFileSync(path.join(OUT, file), Buffer.from(data, 'base64'));
}
(async () => {
  const b = await chromium.launch(); const url = new URL(BASE);
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
  await ctx.addCookies([{ name: 'vm_session', value: COOKIE, domain: url.hostname, path: '/' }]);
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', (e) => errs.push(e.message));
  await p.goto(BASE + '/live'); await p.waitForSelector('.scard img', { timeout: 120000 }); await p.waitForTimeout(1500);
  await p.evaluate(() => { const g = document.querySelector('#sgrid'); if (g) g.scrollIntoView({ block: 'start' }); window.scrollBy(0, -90); }); await p.waitForTimeout(300);
  await webp(p, SHOT);
  if (SHOT !== 'monitor.webp') { await p.setViewportSize({ width: 1600, height: 2400 }); await p.waitForTimeout(500); await webp(p, SHOT.replace('.webp', '-full.webp')); }
  await p.goto(BASE + '/projeto/' + PID); await p.waitForSelector('.clip video', { timeout: 120000 }); await p.waitForTimeout(800);
  const card = await p.$('.clip'); const bb = await card.boundingBox();
  await p.setViewportSize({ width: 1600, height: Math.max(1000, Math.ceil(bb.y + bb.height + 40)) });
  await webp(p, 'estudio.webp', { x: Math.max(0, bb.x - 20), y: Math.max(0, bb.y - 20), width: Math.min(720, bb.width + 40), height: Math.min(1100, bb.height + 40) });
  const mcp = fs.readFileSync(MCP, 'utf8'); const j = JSON.parse(mcp);
  const brief = { plan: j.plan, slots: j.slots, active: j.active, usage: j.usage, test_source: j.test_source,
    streams: j.streams.map((s) => ({ channel: s.channel, slot: s.slot, state: s.state, session: s.session && { status: s.session.status, monitoring_s: s.session.monitoring_s, candidates: s.session.candidates, preview: s.session.preview && { t_stream: s.session.preview.t_stream } } })) };
  const term = await ctx.newPage(); await term.setViewportSize({ width: 1200, height: 760 });
  await term.setContent(`<html><body style="margin:0;background:#0b0b14;font:15px/1.5 ui-monospace,Menlo,monospace;color:#e6e6f3">
    <div style="padding:22px 26px;border-bottom:1px solid #2a2a44;color:#b8b8d2;font-family:system-ui,sans-serif">Claude · ferramenta MCP <b style="color:#fff">clipeiaki · list_connected_streamers</b></div>
    <pre id="j" style="margin:0;padding:22px 26px;white-space:pre-wrap;color:#e6e6f3"></pre></body></html>`);
  await term.$eval('#j', (el, t) => { el.textContent = t; }, JSON.stringify(brief, null, 2).slice(0, 2400));
  await webp(term, 'mcp.webp');
  console.log(errs.length ? 'ERROS JS: ' + errs.join(' | ') : 'capturas ok, sem erros de JS'); await b.close();
})();
