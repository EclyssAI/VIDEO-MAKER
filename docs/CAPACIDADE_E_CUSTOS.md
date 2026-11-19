# ClipeiAki — Capacidade e custos do Live Monitor (3 e 10 transmissões)

Data: 19/11/2026 · Máquina de teste: 4 vCPU, 15,7 GB RAM (contêiner desta sessão) · Harness: `web/tests/load_live.py`
· Relatórios brutos: `docs/evidencias/carga_*.json` · Tabelas geradas por `python -m web.tests.cost_report`.

**Tipos de evidência (nunca misturados):**
- **REAL** — canais da Twitch ao vivo de verdade, escolhidos na hora entre os que estavam ao vivo (lista no JSON).
- **FIXTURE** — VOD real da Twitch (720p60, 3,1 Mbps) tocado em tempo real como se fosse live, um trecho diferente por
  transmissão. Mesma decodificação e análise, **sem rede** e sem a variação de uma live.
- **IA**: nenhuma chamada de API em nenhuma rodada (US$ 0). No modelo final o servidor **não usa** API do Claude: a análise é
  feita pelo Claude do próprio cliente via MCP; o consumo de tokens citado abaixo é uma estimativa do que isso gasta no plano do cliente.

Cada rodada: N transmissões por 6–8 min, um corte pedido por transmissão durante a carga (simula o usuário aprovando um
candidato), **SIGKILL no agente na metade** e retomada automática, depois parada e espera dos renders.

## Medições (valores do JSON de cada rodada)

| Rodada | Tipo | CPU agente (núcleos, média / p95) | Núcleos por transmissão | CPU máquina (média) | RAM agente (média / máx) | Banda por transmissão | Buffer máx | Atraso de processamento p50 / p95 / máx | Detecção evento→candidato p50 / máx | Transcrito | Candidatos/h por transmissão | Cortes pedidos → prontos | Render (s) | Recuperação pós-SIGKILL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 transmissões | FIXTURE (arquivo local tocado como live; sem rede) | 1.17 / 2.27 | 0.391 | 46.5% de 4 vCPU | 857.8 / 1150.0 MB | 3.43 Mbps (1.54 GB/h) | 502.1 MB | 3.0 / 22.7 / 38.6 s | 10.45 / 44.1 s (n=24) | 55% | 79.9 | 3 → 3 (falhas 0) | 23.9, 33.3, 45.7 | 3/3 retomadas em [17.2, 23.2, 25.2] s; buracos: nenhum |
| 10 transmissões (v1, antes da otimização) | FIXTURE (arquivo local tocado como live; sem rede) | 2.36 / 2.75 | 0.236 | 95.7% de 4 vCPU | 1769.6 / 1963.1 MB | 3.43 Mbps (1.54 GB/h) | 1615.2 MB | 56.5 / 114.8 / 136.3 s | 63.0 / 133.6 s (n=82) | 57% | 77.5 | 10 → 10 (falhas 0) | 35.8, 61.5, 96.1, 131.3, 165.6, 206.0, 244.4, 253.5, 290.3, 285.7 | 10/10 retomadas em [6.7, 8.7, 10.7, 12.7, 14.7, 16.7, 18.7, 20.7, 22.7, 24.7] s; buracos: nenhum |
| 10 transmissões (v2) | FIXTURE (arquivo local tocado como live; sem rede) | 2.56 / 3.45 | 0.256 | 89.7% de 4 vCPU | 1708.1 / 1972.6 MB | 3.43 Mbps (1.54 GB/h) | 1592.7 MB | 4.1 / 38.3 / 56.3 s | 13.2 / 58.9 s (n=78) | 46% | 79.0 | 10 → 5 (falhas 0) | 45.4, 90.3, 134.2, 200.7, 271.9 | 10/10 retomadas em [17.2, 21.2, 23.2, 25.2, 27.3, 29.3, 31.3, 33.3, 35.3, 37.3] s; buracos: nenhum |
| 3 transmissões | REAL (Twitch ao vivo) | 1.24 / 2.44 | 0.414 | 41.9% de 4 vCPU | 1135.8 / 1334.1 MB | 3.29 Mbps (1.48 GB/h) | 613.7 MB | 3.1 / 15.7 / 30.7 s | 9.1 / 33.7 s (n=29) | 70% | 72.1 | 3 → 3 (falhas 0) | 13.5, 32.3, 59.9 | 3/3 retomadas em [23.7, 24.7, 27.7] s; buracos: nenhum |
| 10 transmissões (v2) | REAL (Twitch ao vivo) | 2.2 / 3.43 | 0.22 | 88.1% de 4 vCPU | 2397.6 / 2830.3 MB | 3.37 Mbps (1.52 GB/h) | 2169.3 MB | 2.2 / 42.1 / 63.2 s | 10.7 / 70.6 s (n=77) | 39% | 56.0 | 10 → 10 (falhas 0) | 42.8, 52.4, 68.4, 91.4, 134.3, 181.0, 246.6, 174.5, 106.8, 92.3 | 10/10 retomadas em [22.2, 24.2, 26.2, 28.2, 30.2, 32.2, 34.2, 36.2, 38.2, 40.0] s; buracos: nenhum |

## Custo por hora de transmissão monitorada

Base: rodada de 10 transmissões (REAL (Twitch ao vivo)). CPU da máquina inteira (agente + render + web) por transmissão: **0.35 núcleo**. Premissa de VM: US$ 100/mês por 4 vCPU → US$ 0.0342 por núcleo-hora.

- Infraestrutura (CPU): **US$ 0.0121 por transmissão-hora**.
- IA: **US$ 0 para a Eclyss** — não há API do Claude no servidor. A análise contextual é feita pelo Claude do próprio cliente, conectado por MCP. Referência de consumo no plano do cliente por momento revisado (get_highlight + review_moment): ~2000 tokens de entrada (3 frames de 512×288 ≈ 790 tokens + JSON) e 300–1000 de saída. Com 80 candidatos/h por transmissão, revisar todos seria ~160 mil tokens de entrada por transmissão-hora — por isso o roteiro do MCP pede para revisar só os candidatos mais fortes (score) e o painel permite decidir manualmente.

## Custo mensal por assinante usando 100% da franquia

| Plano | Preço | Receita em US$ (sem taxa Cakto, PENDENTE) | Horas/mês | CPU (infra) | Armazenamento dos cortes (acumula por mês) | IA | Total para a Eclyss | % da receita |
|---|---|---|---|---|---|---|---|---|
| Creator | R$ 49.90 | US$ 9.07 | 60 h | US$ 0.72 | US$ 0.16 | US$ 0 (Claude do cliente) | US$ 0.89 | 10% |
| Creator Studio | R$ 69.90 | US$ 12.71 | 200 h | US$ 2.41 | US$ 0.54 | US$ 0 (Claude do cliente) | US$ 2.96 | 23% |

Câmbio de referência R$ 5.50/US$. Sem taxa da Cakto (PENDENTE). Banda de entrada não cobrada pela maioria dos provedores (entrada), mas medida: 1.52 GB por transmissão-hora.


## Leitura dos resultados

| Pergunta | Resposta medida |
|---|---|
| 3 transmissões simultâneas (Creator) numa VM de 4 vCPU | **Tempo real.** Twitch real: atraso p50 3,1 s / p95 15,7 s; detecção p50 9,1 s; 42% da CPU da máquina. |
| 10 transmissões simultâneas (Studio) numa VM de 4 vCPU | **Gravação e detecção em tempo real na mediana** (Twitch real: p50 2,2 s; detecção p50 10,7 s; 88% da CPU), com picos de atraso (p95 42 s) na recuperação após queda forçada e quando renders disputam CPU. **Nenhum bloco perdido** em nenhuma rodada. |
| O que mudou entre v1 e v2 de 10 transmissões | v1: atraso crescia até 136 s (render usando todos os núcleos + transcrição de 57% dos blocos). v2: Whisper ~6x mais leve, imagem por quadro-chave acima de 3 sessões, transcrição só de picos fortes e render em prioridade baixa → p50 de 56 s para 4 s (fixture) e 2,2 s (real). |
| Gargalo restante | **Render**: um worker sequencial. Com 10 cortes pedidos de uma vez, o último ficou pronto em ~4 min. Para Studio em produção: worker de render separado (ou VM de 8 vCPU) e mais de um worker. |
| Recuperação | SIGKILL no agente: 100% das sessões retomadas em 7–40 s, linha do tempo contínua (sem buracos) em todas as rodadas. |
| Memória | Agente: ~1,1 GB (3 transmissões) a ~2,4–2,8 GB (10 transmissões, 2 modelos Whisper). |
| Banda | 3,3–3,4 Mbps por transmissão (720p60) = ~34 Mbps para 10; ~1,5 GB por transmissão-hora de entrada. |
| Disco temporário | Buffer de 10–15 min: ~0,6 GB (3) a ~2,2 GB (10); apagado ao encerrar. |
| Custo de IA | **Zero para a Eclyss**: a análise é feita pelo Claude do cliente via MCP. |

## Capacidade e dimensionamento (recomendação)

- **1 VM de 4 vCPU / 16 GB ≈ 10 transmissões simultâneas** (`LIVE_CAPACITY_TOTAL=10`), com o render em outra máquina ou em
  prioridade baixa. O custo por hora é baixo (~US$ 0,012 por transmissão-hora), mas a capacidade precisa ser provisionada
  para o **pico**: um assinante Studio usando as 10 telas ao mesmo tempo ocupa uma VM inteira enquanto estiver ao vivo.
- Escala horizontal: vários processos `web.live.agent` (cada um com `LIVE_MAX_SESSIONS`) disputam as sessões pelo lease no
  banco; para mais de uma VM é preciso migrar SQLite → Postgres e os arquivos para armazenamento compartilhado (plano em
  `docs/LIVE_AGENT_BETA.md` §2.3).
- Capacidade Beta separada (`LIVE_CAPACITY_BETA`, padrão 2) para contas gratuitas não ocuparem a capacidade dos pagantes.

## Proposta de franquias e uso justo (PARA APROVAÇÃO)

| | Creator | Creator Studio | Racional |
|---|---|---|---|
| Transmissões simultâneas | 3 | 10 | Definido por você; aplicado no backend. |
| Horas de monitoramento/mês | **60 h** | **200 h** | ≈ 2 h/dia (Creator) e ≈ 6,7 h/dia somando as telas (Studio). Custo de infraestrutura a 100% de uso: 10% e 23% da receita. Não prometemos 24/7 nem ilimitado. |
| Cortes de live/mês | **150** | **500** | ~5 e ~16 por dia; armazenamento acumulado ~2,7 GB e ~9 GB/mês. |
| Duração máxima por sessão | 2 h | 4 h | Mantido do plano anterior; nova sessão pode ser iniciada em seguida. |
| Uso justo | Inícios de sessão limitados a 30/h por conta; só canais ao vivo; capacidade total do servidor pode recusar novos inícios com aviso, sem cobrança extra. | | |

Pendências para fechar o preço: taxa da Cakto por transação e câmbio/contrato de hospedagem reais.

