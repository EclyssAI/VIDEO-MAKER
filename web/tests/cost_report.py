"""Relatório de capacidade e custos a partir das medições de carga (docs/evidencias/carga_*.json).
Uso: python -m web.tests.cost_report > docs/CAPACIDADE_E_CUSTOS_medido.md
Todas as premissas de preço ficam no topo e aparecem no relatório; nada é apresentado como medido se não foi."""
import json, pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
EV = ROOT / "docs/evidencias"
PLANS = yaml.safe_load((ROOT / "config/plans.yaml").read_text())["plans"]

# ---------------- premissas (ajustáveis; NÃO medidas) ----------------
VM_USD_MONTH, VM_CORES = 100.0, 4          # VM 4 vCPU dedicadas / 16 GB (referência de mercado nov/2026, a confirmar com o provedor)
CORE_HOUR = VM_USD_MONTH / (VM_CORES * 730)
STORAGE_USD_GB_MONTH = 0.06                # disco/objeto (referência, a confirmar)
CLIP_MB = 18.6                             # corte de 45 s medido no teste de navegador (docs/AUDITORIA_WEB.md)
USD_BRL = 5.50                             # câmbio de referência (ajustar)
CAKTO_FEE = None                           # taxa da Cakto por transação: PENDENTE (não informada)
# Claude por análise (3 frames 512x288 ≈ 262 tokens cada, prompt+schema+contexto ≈ 1.200 tokens; saída JSON + raciocínio 300–1.000)
IN_TOK, OUT_LOW, OUT_HIGH = 2000, 300, 1000
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}
CALLS_MAX_PER_HOUR = 3600 / 30             # o detector espera 30 s entre candidatos (LIVE_COOLDOWN_S) → teto de 120 análises/h


def load(name):
    p = EV / f"carga_{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def call_cost(model, out):
    pin, pout = PRICES[model]; return IN_TOK * pin / 1e6 + out * pout / 1e6


def main():
    runs = {k: load(k) for k in ("fixture_3", "fixture_10", "fixture_10_v2", "real_3", "real_10")}
    print("## Medições (valores do JSON de cada rodada)\n")
    print("| Rodada | Tipo | CPU agente (núcleos, média / p95) | Núcleos por transmissão | CPU máquina (média) | RAM agente (média / máx) | Banda por transmissão | Buffer máx | Atraso de processamento p50 / p95 / máx | Detecção evento→candidato p50 / máx | Transcrito | Candidatos/h por transmissão | Cortes pedidos → prontos | Render (s) | Recuperação pós-SIGKILL |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k, r in runs.items():
        if not r: print(f"| {k} | — | não executada | | | | | | | | | | | | |"); continue
        lag, det, rec, ren = r["processing_lag_s"], r["detection_latency_s"], r["recovery"], r["render"]
        tag = " (v1, antes da otimização)" if k == "fixture_10" else " (v2)" if k.endswith("_v2") or k == "real_10" else ""
        print(f"| {r['streams']} transmissões{tag} | {r['evidence_type']} | {r['cpu_cores_agent']['mean']} / {r['cpu_cores_agent']['p95']} | {r['cpu_cores_per_stream']} | "
              f"{r['machine_cpu_pct_mean']}% de {r['machine']['cpus']} vCPU | {r['rss_mb_agent']['mean']} / {r['rss_mb_agent']['max']} MB | {r.get('input_mbps_per_stream')} Mbps "
              f"({r.get('input_gb_per_stream_hour')} GB/h) | {r['buffer_mb_max']} MB | {lag['p50']} / {lag['p95']} / {lag['max']} s | {det['p50']} / {det['max']} s (n={det['n']}) | "
              f"{round(r['transcribed_fraction'] * 100)}% | {r['candidates_per_stream_hour']} | {ren['requested']} → {ren['ready']} (falhas {ren['failed']}) | "
              f"{', '.join(str(x) for x in ren['render_s']) or '—'} | {rec['resumed_sessions']}/{r['streams']} retomadas em {rec['resume_after_kill_s']} s; buracos: {rec['gaps_after_recovery'] or 'nenhum'} |")
    base = runs.get("real_10") or runs.get("fixture_10_v2") or runs.get("real_3") or runs.get("fixture_3")
    if not base: return
    mach_cores_stream = base["machine_cpu_pct_mean"] / 100 * base["machine"]["cpus"] / base["streams"]
    cand_h = max(r["candidates_per_stream_hour"] for r in runs.values() if r)
    calls_h = min(cand_h, CALLS_MAX_PER_HOUR)
    infra_h = mach_cores_stream * CORE_HOUR
    print(f"\n## Custo por hora de transmissão monitorada\n")
    print(f"Base: rodada de {base['streams']} transmissões ({base['evidence_type']}). CPU da máquina inteira (agente + render + web) por transmissão: "
          f"**{mach_cores_stream:.2f} núcleo**. Premissa de VM: US$ {VM_USD_MONTH:.0f}/mês por {VM_CORES} vCPU → US$ {CORE_HOUR:.4f} por núcleo-hora.\n")
    print(f"- Infraestrutura (CPU): **US$ {infra_h:.4f} por transmissão-hora**.")
    print(f"- IA (só se ativada): até {cand_h:.0f} candidatos/h medidos; teto de {CALLS_MAX_PER_HOUR:.0f} análises/h pelo intervalo entre candidatos. Custo por análise estimado "
          f"({IN_TOK} tokens de entrada, {OUT_LOW}–{OUT_HIGH} de saída):")
    for m in PRICES:
        lo, hi = call_cost(m, OUT_LOW), call_cost(m, OUT_HIGH)
        print(f"  - `{m}`: US$ {lo:.4f}–{hi:.4f} por análise → **US$ {lo * calls_h:.2f}–{hi * calls_h:.2f} por transmissão-hora** se todo candidato for analisado.")
    print(f"\n## Custo mensal por assinante usando 100% da franquia\n")
    print("| Plano | Preço | Receita em US$ (sem taxa Cakto, PENDENTE) | Horas/mês | Infra | Armazenamento dos cortes | IA Haiku 5.5 | IA Sonnet 5.5 | IA Opus 5.5 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for k in ("creator", "studio"):
        L = PLANS[k]; h = L["live_hours_per_month"]; rev = L["price_brl"] / USD_BRL
        stor = L["live_clips_per_month"] * CLIP_MB / 1024 * STORAGE_USD_GB_MONTH
        ia = {m: (call_cost(m, OUT_LOW) * calls_h * h, call_cost(m, OUT_HIGH) * calls_h * h) for m in PRICES}
        cap = L["live_budget_usd_max"] * h * 60 / L["live_max_minutes"]  # teto pelo orçamento por sessão
        cell = lambda m: f"US$ {min(ia[m][0], cap):.2f}–{min(ia[m][1], cap):.2f}"
        print(f"| {L['label']} | R$ {L['price_brl']:.2f} | US$ {rev:.2f} | {h} h | US$ {infra_h * h:.2f} | US$ {stor:.2f}/mês acumulado | {cell('claude-haiku-5-5')} | "
              f"{cell('claude-sonnet-5-5')} | {cell('claude-opus-5-5')} |")
    print(f"\nTeto de IA por mês já limitado pelo orçamento por sessão do plano (US$ {PLANS['creator']['live_budget_usd_max']:.2f} por sessão de "
          f"{PLANS['creator']['live_max_minutes'] / 60:g} h no Creator; US$ {PLANS['studio']['live_budget_usd_max']:.2f} por {PLANS['studio']['live_max_minutes'] / 60:g} h no Studio). "
          f"Câmbio de referência R$ {USD_BRL:.2f}/US$.")


if __name__ == "__main__": main()
