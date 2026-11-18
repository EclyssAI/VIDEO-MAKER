// Teste de fluxo no navegador real (Playwright). Uso: BASE=https://app.exemplo.com MEDIA=/caminho/clip.mp4 OUT=/tmp node web/tests/ui_flow.js
// Serve também como smoke test pós-deploy: cria uma conta nova, envia o vídeo, espera o corte, aprova e baixa.
const BASE = process.env.BASE || 'http://localhost:8000', MEDIA = process.env.MEDIA, OUT = process.env.OUT || '/tmp';
const EMAIL = process.env.EMAIL || `smoke+${Date.now()}@exemplo.com`;
const { chromium } = require('playwright'); const fs = require('fs');
(async () => {
  const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1280, height: 860 }, acceptDownloads: true });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  const t0 = Date.now(); const log = (m) => console.log(`[${((Date.now()-t0)/1000).toFixed(1)}s] ${m}`);
  await p.goto('' + BASE + '/criar-conta'); await p.fill('#name', 'Carla Teste'); await p.fill('#email', EMAIL);
  await p.fill('#pw', 'senha-forte-123'); await p.click('button[type=submit]'); await p.waitForSelector('text=Nenhum projeto ainda'); log('signup ok -> painel vazio');
  await p.click('.side a.cta'); await p.setInputFiles('#file', MEDIA); await p.fill('#pname', 'Upload pelo navegador');
  await p.click('#nsub'); await p.waitForURL(/\/projeto\//, { timeout: 120000 }); log('upload ok -> ' + p.url());
  await p.screenshot({ path: '' + OUT + '/flow-1-processing.png' });
  await p.waitForSelector('[data-act=approve]', { timeout: 300000 }); log('processado: corte pronto para revisão');
  await p.screenshot({ path: '' + OUT + '/flow-2-ready.png' });
  const ok = await p.$eval('video', v => new Promise(r => { v.muted = true; v.currentTime = 3; v.onseeked = () => r({ w: v.videoWidth, h: v.videoHeight, d: v.duration }); v.load(); v.currentTime = 3; }));
  log('preview no <video>: ' + JSON.stringify(ok));
  await p.click('[data-act=approve]'); await p.waitForSelector('a:has-text("Baixar MP4")'); log('aprovado');
  const [dl] = await Promise.all([p.waitForEvent('download'), p.click('a:has-text("Baixar MP4")')]);
  const f = '' + OUT + '/flow-download.mp4'; await dl.saveAs(f); log('download: ' + dl.suggestedFilename() + ' ' + fs.statSync(f).size + ' bytes');
  await p.click('.side a[href="/biblioteca"]'); await p.waitForSelector('.clips .clip'); await p.screenshot({ path: '' + OUT + '/flow-3-biblioteca.png' }); log('biblioteca com o corte aprovado');
  console.log(errs.length ? 'ERROS: ' + errs.join(' | ') : 'sem erros de JS'); await b.close();
})();
