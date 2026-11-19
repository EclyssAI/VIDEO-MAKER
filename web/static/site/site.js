"use strict";
/* Landing do ClipeiAki: entrada suave das seções (desligada em prefers-reduced-motion) e estado real do checkout.
   Nada aqui inventa dados: os planos vêm do HTML gerado a partir de config/plans.yaml e o checkout só aparece se o backend
   disser que a cobrança está habilitada (/api/public/plans). */
(function () {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduce && "IntersectionObserver" in window) {
    document.documentElement.classList.add("js");
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
  }
  fetch("/api/public/plans", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : null)).then((d) => {
    if (!d) return;
    document.querySelectorAll("[data-plan]").forEach((a) => {
      const url = d.checkout_enabled && d.checkout && d.checkout[a.dataset.plan];
      if (url) { a.href = url; a.textContent = "Assinar " + a.dataset.label; a.removeAttribute("aria-disabled"); a.rel = "noopener"; }
    });
  }).catch(() => { /* sem rede: mantém o estado estático (assinaturas em breve) */ });
})();
