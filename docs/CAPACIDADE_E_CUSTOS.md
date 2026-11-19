# ClipeiAki — Capacidade e custos do Live Monitor (3 e 10 transmissões)

Data: 19/11/2026 · Máquina de teste: 4 vCPU, 15,7 GB RAM (contêiner desta sessão) · Harness: `web/tests/load_live.py`
· Relatórios brutos: `docs/evidencias/carga_*.json` · Tabelas geradas por `python -m web.tests.cost_report`.

**Tipos de evidência (nunca misturados):**
- **REAL** — canais da Twitch ao vivo de verdade, escolhidos na hora entre os que estavam ao vivo (lista no JSON).
- **FIXTURE** — VOD real da Twitch (720p60, 3,1 Mbps) tocado em tempo real como se fosse live, um trecho diferente por
  transmissão. Mesma decodificação e análise, **sem rede** e sem a variação de uma live.
- **Claude**: desligado em todas as rodadas (sem `ANTHROPIC_API_KEY`) → 0 chamadas, US$ 0. Custos de IA abaixo são
  **estimativas** a partir de tokens e preços oficiais, não medição.

Cada rodada: N transmissões por 6–8 min, um corte pedido por transmissão durante a carga (simula o usuário aprovando um
candidato), **SIGKILL no agente na metade** e retomada automática, depois parada e espera dos renders.

{{TABELAS}}
