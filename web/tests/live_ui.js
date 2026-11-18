// Teste/demonstração do Claude Live Monitor em navegador real (Playwright), com gravação de vídeo.
// Uso: BASE=http://127.0.0.1:8850 EMAIL=... PASS=... SID=<sessão> OUT=<dir> SECONDS=120 MODE=real|sim node web/tests/live_ui.js
// Verifica: timeline vinda do backend (SSE), preview do corte tocando e — quando houve análise — que a imagem exibida como
// "Último frame enviado à IA" tem o MESMO sha256 registrado no evento de análise (bytes que foram para a API).
const { chromium } = require("playwright");
const { BASE, EMAIL, PASS, SID, OUT = "/tmp", SECONDS = "120", MODE = "real" } = process.env;
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: OUT, size: { width: 1440, height: 900 } } });
  const p = await ctx.newPage(); const errs = [];
  p.on("pageerror", (e) => { if (!/getLayoutMap/.test(e.message)) errs.push(e.message); });  // getLayoutMap: script interno do player da Twitch
  const t0 = Date.now(); const log = (m) => console.log(`[${((Date.now() - t0) / 1000).toFixed(0)}s] ${m}`);
  await p.goto(`${BASE}/entrar`); await p.fill("#email", EMAIL); await p.fill("#pw", PASS); await p.click("button[type=submit]");
  await p.waitForSelector(".live-dash"); await p.waitForTimeout(1500);
  await p.goto(`${BASE}/live/${SID}`); await p.waitForSelector("#ltl"); log("monitor aberto");
  let clicked = false, played = false;
  while (Date.now() - t0 < Number(SECONDS) * 1000) {
    await p.waitForTimeout(3000);
    if (MODE === "real" && !clicked) {
      const btn = await p.$("[data-mclip]");
      if (btn) { await btn.scrollIntoViewIfNeeded(); await btn.click(); clicked = true; log("Criar corte clicado"); }
    }
    const v = await p.$("#lclips video");
    if (v && !played) {
      await v.scrollIntoViewIfNeeded(); await p.waitForTimeout(800);
      const ok = await v.evaluate((el) => new Promise((r) => { el.muted = true; el.play().then(() => setTimeout(() => r({ t: el.currentTime, w: el.videoWidth, h: el.videoHeight }), 2500)).catch((e) => r({ err: String(e) })); }));
      log("preview tocando: " + JSON.stringify(ok)); played = true; await p.waitForTimeout(4000);
      await p.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    }
  }
  const tl = await p.$$eval("#ltl li", (l) => l.map((x) => x.innerText.replace(/\s+/g, " ")).slice(0, 6));
  log("timeline (mais recentes): " + JSON.stringify(tl));
  log("status Claude: " + (await p.textContent("#lclaude")).replace(/\s+/g, " ").slice(0, 160));
  const img = await p.$(".lframe img");
  if (img) {
    const r = await img.evaluate(async (el) => {
      const buf = await (await fetch(el.src)).arrayBuffer(); const h = await crypto.subtle.digest("SHA-256", buf);
      return { shown: [...new Uint8Array(h)].map((x) => x.toString(16).padStart(2, "0")).join(""), caption: el.parentElement.innerText };
    });
    const s = await (await p.request.get(`${BASE}/api/live/sessions/${SID}`)).json();
    const frames = s.last_analysis ? s.last_analysis.frames.map((f) => f.sha256) : [];
    log(`frame exibido sha256=${r.shown.slice(0, 16)}… | registrado na análise: ${frames.includes(r.shown) ? "SIM (mesmos bytes enviados à API)" : "NÃO"}`);
    if (!frames.includes(r.shown)) errs.push("frame exibido não corresponde ao frame analisado");
  } else log("nenhum frame enviado à IA (exibido como tal)");
  if (!played) errs.push("nenhum preview de corte tocou");
  await p.screenshot({ path: `${OUT}/live_monitor_${MODE}.png`, fullPage: true });
  const video = p.video(); await ctx.close(); console.log("VIDEO", await video.path());
  console.log(errs.length ? "ERROS: " + errs.join(" | ") : "OK sem erros"); await b.close(); process.exit(errs.length ? 1 : 0);
})();
