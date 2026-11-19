# ClipeiAki — esteira de cortes de GTA
**captar → cortar em vários momentos → template + título + legenda (transcrição/tradução) → aprovar → postar (TikTok, Reels, Shorts)**

| Etapa | Comando | Clone de (ViceScale) |
|---|---|---|
| Virais gringos | `python esteira.py scrap` (config/sources.yaml) | ViceScrap + ViceRepost |
| Lives madrugada | `python esteira.py live` (config/live.yaml, ciclos de 30 min) | — |
| Qualquer vídeo/VOD | `python esteira.py add <arquivo/link>` | Editor vertical |
| Títulos/legendas | Claude + skill `/viralizei` escreve `work/batch/<lote>/copy.json` (lê só `for_claude.txt`) | Multiplicador de conteúdo |
| Render | `python esteira.py render <lote>` → `output/<lote>/NN_slug/{video.mp4,thumb.jpg,descricao.txt,meta.json}` | Editor |
| Aprovar | `python esteira.py approve <lote> 1 3` → agenda nos horários de pico | Agendador |
| Postar | automático no ciclo, ou `python esteira.py post` / `status` | Agendador multi-rede |

Pastas: `capture/` captação · `live/` detecção+render · `publish/` APIs + fila · `template/` assets do canal · `config/` · `work/` (temp) · `output/` (entregas) · `logs/` (fila, vistos).
Instalação: `pip install yt-dlp streamlink faster-whisper pyyaml requests google-api-python-client google-auth-oauthlib` + ffmpeg; `python live/setup_assets.py`.
Skills: viralizei, find-skills, superpowers, sound, viral-tiktok-hooks. MCP: REA (`.mcp.json`).

---

## ClipeiAki Web (SaaS, ex-VIDEO-MAKER) — `web/`
Versão para navegador que reaproveita o motor acima (`live/detect.py`, `live/render_live.py`, `capture/stack.py`) sem alterá-lo.
Auditoria, matriz de funcionalidades, arquitetura e veredito: **`docs/AUDITORIA_WEB.md`**.

```bash
pip install -r requirements-web.txt            # + ffmpeg com libass e fonte Inter
BETA_SIGNUP=1 COOKIE_SECURE=0 uvicorn web.app:app --port 8000   # interface + API
BETA_SIGNUP=1 python -m web.worker                               # processamento (outro terminal)
VM_TEST_MEDIA=/pasta/com/videos pytest -v web/tests/test_e2e.py  # testes ponta a ponta reais
```
Produção: `cp .env.example .env` e `docker compose up -d --build` (web + worker, volume `/data`). Limites dos planos em `config/plans.yaml`.

### Claude Live Agent + Live MCP
Monitoramento de lives da Twitch com análise do Claude e cortes automáticos: **`docs/LIVE_AGENT_BETA.md`** (estado, testes reais × simulados, custos, plano Vercel).
```bash
python -m web.live.agent                                          # processo contínuo de gravação/análise (3º terminal)
VM_TEST_MEDIA=/pasta pytest -v web/tests/test_live.py             # [SIM] agente, orçamento, falhas, isolamento, MCP
LIVE_REAL=1 pytest -v -s web/tests/test_live_real.py              # [REAL] live de verdade na Twitch
```
MCP: `<PUBLIC_URL>/mcp` com token pessoal (Conta → ClipeiAki Live MCP) ou `CLIPEIAKI_TOKEN=... python -m web.mcp_server` (stdio).

### Live Monitor multi-transmissão, landing e jurídico (v0.7.0)
- Landing: `/` para visitantes; fonte em `web/site_src/index.html`; planos vêm de `config/plans.yaml`. Gerar: `python -m web.site_build`.
- Documentos: `/termos`, `/privacidade`, `/cancelamento`, `/conteudo`, `/cookies`, `/regras-live-ia`, `/contato` (`web/legal_build.py`).
- Relatório da entrega, PASS/BLOCKED e bloqueios de venda: **`docs/ENTREGA_LIVE_MONITOR.md`**. Capacidade e custos: `docs/CAPACIDADE_E_CUSTOS.md`.
  Riscos jurídicos: `docs/RISCOS_JURIDICOS.md`.
```bash
pytest -v web/tests/test_monitor.py                                    # limites 3/10, isolamento, aceite, MCP (sem vídeo)
python -m web.tests.load_live --mode real --streams 10 --minutes 8 --out carga.json   # carga com lives reais da Twitch
BASE=http://127.0.0.1:8000 NODE_PATH=<axe-core> node web/tests/landing_check.js       # landing: responsivo + WCAG
```
