# ClipeiAki v0.7.0 — Landing comercial, Live Monitor 3/10, MCP e proteção jurídica

Data: 19/11/2026 · Branch: `claude/busy-gates-22tasn` (a partir de `22fea8a`, último commit do app web) · Evidências: `docs/evidencias/`

> Nada foi publicado em produção, nenhuma cobrança foi habilitada, nenhum serviço pago foi contratado e a API paga do
> Claude não foi ativada. Os bloqueios P0 anteriores continuam (Cakto desligada, plano pago só com e-mail verificado).

{{RESUMO}}

## 1. Ponto de partida (verificado)

| Item | Achado |
|---|---|
| Landing existente | **Não está no repositório** (nem em outras branches; a auditoria anterior registra que "a landing não foi tocada" e vive fora do GitHub/Vercel sem acesso nesta sessão). Por isso a nova landing foi criada no próprio app, com a identidade visual do app (mesmos tokens de cor, fonte e componentes), servida em `/` para visitantes. O projeto Vercel e a landing atual **não foram alterados**. |
| App | FastAPI + SPA sem dependências (branch `claude/awesome-noether-nuave7`), trazido para esta branch por *fast-forward*. Suítes existentes no commit original: e2e 7/7 (relatório anterior), live/MCP simulado **6/6 reexecutado aqui** antes das mudanças (388 s). |
| Live Monitor anterior | 1 canal por sessão, **1 sessão por usuário**; MCP com 10 ferramentas. |
| Cakto | Integração por webhook pronta e **desligada** (`CAKTO_ENABLED=0`). IDs de oferta vêm de variáveis de ambiente (`CAKTO_OFFER_CREATOR`, `CAKTO_OFFER_STUDIO`), vazias. |
| Skills (`/find-skills`) | Busca feita (`npx skills find`): `anthropics/skills@frontend-design` (1,1 mi instalações), `emilkowalski/skills@animation-performance` (97 mil), `mastepanoski/claude-skills@wcag-accessibility-audit` (1,6 mil), `manutej/...@playwright-visual-testing` (1,4 mil). **A instalação de skills de terceiros foi bloqueada pela política de permissões do ambiente**; usei a skill `ui-ux-pro-max` já versionada no repositório (sistema de design, padrões de landing/pricing/FAQ, regras de acessibilidade e movimento) e auditoria WCAG com `axe-core` nos testes. |

{{SECOES}}
