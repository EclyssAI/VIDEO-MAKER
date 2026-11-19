# ClipeiAki v0.7.0 — Relatório único da entrega

Landing comercial, Live Monitor 3/10, MCP com o Claude do cliente, capacidade e custos, e proteção jurídica.

Data: 19/11/2026 · Branch: `claude/busy-gates-22tasn` (a partir de `22fea8a`, último commit do app web) · Evidências: `docs/evidencias/`

> **Não foi feito:** nada foi publicado em produção, nenhuma cobrança foi habilitada, nenhum serviço pago foi contratado e
> nenhuma API paga de IA foi ativada. Os bloqueios P0 anteriores continuam: Cakto desligada (`CAKTO_ENABLED=0`) e plano
> pago aplicado só a e-mail verificado.

## 0. Resumo executivo

| Pedido | Situação |
|---|---|
| 1. Landing com ~3 min de leitura | **PASS.** 9 seções, 533 palavras de texto principal + tabela de consulta. Responsiva em 4 larguras, 0 violações WCAG 2.1 AA. Servida em `/` para visitantes. |
| 2. Cards comerciais | **PASS** para cards, matriz e limites aplicados no backend. As franquias mensais são **PROPOSTA para aprovação**. Os IDs das ofertas na Cakto ficaram **BLOCKED** (sem acesso ao painel). |
| 3. Live Monitor 3 e 10 telas | **PASS.** Grade com preview real, status, duração, candidatos, ações e histórico. O limite é aplicado no backend; a 4ª e a 11ª transmissões são bloqueadas. |
| 4. MCP com Claude | **PASS (com ressalva).** Mudança pedida durante o trabalho: **sem API do Claude no servidor**. O Claude do próprio cliente se conecta por um **conector OAuth** e decide os cortes pelo MCP. Fluxo testado de ponta a ponta com o cliente MCP oficial. Falta o teste com o Claude real do claude.ai, que exige uma URL pública (**BLOCKED**). |
| 5. Capacidade e custos | **PASS.** Medido com Twitch real (3 e 10 canais) e com fixture (3 e 10). 10 transmissões rodam em tempo real na mediana numa VM de 4 vCPU; o gargalo restante é o render. O custo de infraestrutura fica entre 10% e 23% da receita com a franquia inteira usada; IA custa US$ 0 para a Eclyss. |
| 6. Jurídico | **PASS (rascunho para validação).** 7 páginas próprias, aceite versionado, exportação e exclusão de dados, registros de acesso por 6 meses e revisão de riscos com fontes. Os dados da empresa estão marcados `PENDENTE_DADO_EMPRESARIAL`. |
| 7. Testes | **PASS:** 14 + 6 + 7 + 1 testes automatizados, checagem da landing no navegador, 5 rodadas de carga e revisão de segurança independente com as 6 correções aplicadas. |

## 1. Ponto de partida (verificado)

| Item | Achado |
|---|---|
| Landing existente | Não está no repositório nem em outras branches; ela fica fora do GitHub, num projeto Vercel sem acesso nesta sessão. A nova landing foi feita **no próprio app**, com a identidade visual dele (tokens de cor, fonte e componentes). O projeto Vercel e a landing atual **não foram alterados**. |
| App | FastAPI + SPA sem dependências, da branch `claude/awesome-noether-nuave7`, trazido para esta branch por *fast-forward*. Linha de base: live/MCP simulado **6/6** no commit original, reexecutado aqui. |
| Live Monitor anterior | 1 canal por sessão e 1 sessão por usuário; MCP com 10 ferramentas e só token pessoal. |
| `/find-skills` | Busca feita com `npx skills find`. Candidatas: `anthropics/skills@frontend-design` (1,1 mi instalações), `emilkowalski/skills@animation-performance` (97 mil), `mastepanoski/claude-skills@wcag-accessibility-audit` (1,6 mil), `manutej/…@playwright-visual-testing` (1,4 mil). **A política de permissões do ambiente bloqueou a instalação de skills de terceiros.** Usei a `ui-ux-pro-max`, já versionada no repo (padrões de landing/pricing/FAQ, acessibilidade e movimento), e auditoria WCAG com `axe-core` nos testes. |
| `/mcp__rea__investigate_feature` | Essa ferramenta não existe no REA deste ambiente. Usei `mcp__rea__analyze_web_bundle`, que tem a mesma função (§5.1). |

## 2. Landing — antes × depois

| | Antes | Depois |
|---|---|---|
| Onde | Landing fora do repositório (sem acesso). No app, o visitante caía direto no login, com um bloco de 3 passos (`docs/evidencias/ui_login.jpg`). | `/` para visitantes serve a landing nova (`web/static/site/index.html`, gerada de `web/site_src/index.html` por `python -m web.site_build`). Quem está logado continua indo para o painel. |
| Conteúdo | ~40 palavras, sem planos, sem FAQ e sem documentos jurídicos. | As 9 seções na ordem pedida: hero, problema, como funciona, 9 módulos com status real, monitoramento simultâneo, exemplos reais, planos (cards + tabela comparativa), FAQ (8 perguntas), CTA final e rodapé jurídico. **533 palavras** de texto principal (≈ 2,7 min) + tabela. |
| Honestidade | — | "Análise com seu Claude" e MCP marcados como **Beta**, Templates como **Parcial**. Nada de depoimentos, clientes ou métricas inventados, nem promessa de 24/7 ou ilimitado. As demonstrações são **capturas reais do app**; como as "lives" são trechos de *Tears of Steel* (Blender Foundation, CC BY 3.0), a legenda e a interface avisam "fonte de teste" (sem streamers sem autorização). |
| Planos | — | Gerados de `config/plans.yaml`, a mesma fonte que o backend usa para bloquear. O CTA mostra "Criar conta · assinaturas em breve" enquanto a Cakto estiver desligada, e vira "Assinar" só quando `/api/public/plans` informar checkout habilitado. |
| Técnica | — | HTML/CSS/JS sem dependências e compatível com a CSP do app (nada inline). Sem fontes externas. Imagens WebP com dimensões fixas e `loading=lazy`. Entrada suave de 380 ms, desligada em `prefers-reduced-motion`. FAQ com `<details>` nativo. Botões com contraste ≥ 5:1 (corrigido também no app). |

Evidências: `docs/evidencias/landing_desktop_1280.jpg`, `landing_mobile_375.jpg`, `landing_check.json`, `juridico_termos_1280.jpg`.

## 3. Planos — matriz de recursos (o que o backend aplica)

| Recurso | Beta (convite) | **Creator R$ 49,90/mês** | **Creator Studio R$ 69,90/mês** | Onde é aplicado |
|---|---|---|---|---|
| Transmissões conectadas e simultâneas | 1 | **3** | **10** | `service.connect_stream/start_stream`, em transação `BEGIN IMMEDIATE` |
| Horas de monitoramento/mês (**PROPOSTA**) | 2 h | 60 h | 200 h | `plans.charge_live` a cada bloco; o agente para por `quota` |
| Cortes de live/mês (**PROPOSTA**) | 10 | 150 | 500 | Rechecado dentro da transação do corte |
| Duração máxima por sessão | 30 min | 2 h | 4 h | `agent.limit_reached` |
| Uploads: projetos / minutos por mês | 3 / 30 | 30 / 600 | 60 / 1.500 | `plans.check_new_project` |
| Duração / tamanho por vídeo | 15 min / 500 MB | 90 min / 2 GB | 180 min / 4 GB | idem |
| Cortes por vídeo enviado | 3 | 6 | 10 | worker |
| Legenda karaokê, webcam, moldura com @ | ✓ | ✓ | ✓ | motor (`render_live.py`) |
| Zoom no pico + efeitos sonoros (premium) | — | — | ✓ | `premium_assets` |
| Exportação | MP4 1080×1920 30 fps | idem | idem | motor |
| Preview, Biblioteca, download após aprovação | ✓ | ✓ | ✓ | API |
| Análise pelo seu Claude (MCP, OAuth) | ✓ | ✓ | ✓ | `web/oauth.py` + `web/mcp_server.py` |
| Recorrência / cancelamento | — | mensal; cancela quando quiser; acesso até o fim do período | idem | Cakto + `billing.py` |

**Exclusivos do Studio:** 10 transmissões simultâneas, efeitos premium, sessões de 4 h, uploads maiores e mais cortes por vídeo.
Justificativa das franquias propostas: `docs/CAPACIDADE_E_CUSTOS.md`.

### Cakto — IDs das ofertas: **BLOCKED**
Não há acesso ao painel nem à API da Cakto nesta sessão, e não pedi credencial para não expor segredo no chat.
O código identifica o plano **só** pelo `offer.id` do webhook, comparando com `CAKTO_OFFER_CREATOR` e `CAKTO_OFFER_STUDIO`
(`web/billing.py:plan_for_offer`). Para corrigir a identificação do Creator:
1. No painel da Cakto, abra a oferta de **R$ 49,90/mês** e copie o ID para `CAKTO_OFFER_CREATOR`. Faça o mesmo com a de **R$ 69,90/mês** em `CAKTO_OFFER_STUDIO`.
2. Confira o nome exibido no checkout ("ClipeiAki Creator" / "ClipeiAki Creator Studio"). O nome não afeta a liberação do acesso.
3. **Não** altere valores. Antes de ligar a cobrança, mande um evento de teste assinado (`test_cakto_webhooks` cobre a lógica).

## 4. Live Monitor — demonstração

- **Slots por plano no backend:** cada slot é uma linha de `live_streams` (um canal), com a declaração "titular/autorizado" e a data.
  - Conectar a 4ª transmissão (Creator) ou a 11ª (Studio) devolve **403**. Iniciar acima do limite também é recusado.
  - Corrida de 6 inícios simultâneos: exatamente 3 aceitos.
  - Rebaixamento Studio → Creator bloqueia os slots 4–10, e o agente para as sessões acima do novo limite.
- **Grade:** 3 ou 10 telas com preview real (o último frame gravado, extraído na mesma decodificação da detecção). Cada tela mostra:
  - canal, plataforma e status (ao vivo, iniciando, reconectando, encerrando, offline, erro, pausado, limite);
  - tempo monitorado, tempo gravado, candidatos, cortes e motivo da última parada;
  - botões iniciar, pausar, remover e inspecionar; abaixo da grade fica o histórico de sessões.
  - A página de inspeção mostra a linha do tempo de eventos reais via SSE, inclusive "frames mostrados ao seu Claude" e "decisão do seu Claude (MCP)".
- **Workers:** a gravação e a análise rodam no processo contínuo `web.live.agent` (lease, heartbeat e retomada); o render roda no `web.worker` (em `nice` no compose). Nada depende de aba aberta ou de função serverless.
- **Só canais ao vivo:** o servidor consulta a Twitch antes de iniciar. Há também limite de 30 inícios por hora e capacidade separada para contas Beta.
- **Fonte de teste sinalizada:** com `LIVE_SOURCE_OVERRIDE` (só em testes), a interface mostra "Fonte de teste (arquivo local)" e um aviso no topo.
- Capturas reais: `web/static/site/media/monitor.webp` (3 telas, fonte CC BY). Na carga com Twitch real, a grade de 10 telas rodou com kaicenat, gaules, jynxzi, zackrawrr, auronplay, elmariana, kamet0, squeezie, tumblurr e lirik (`docs/evidencias/carga_real_10.json`).

## 5. MCP com o Claude do cliente

### 5.1 Investigação do ViceScale (só páginas públicas, sem login, sem copiar código)
- Os metadados públicos mostram o padrão do concorrente (`docs/evidencias/vicescale_mcp_publico.json`):
  - servidor MCP HTTP como recurso protegido (RFC 9728, `/.well-known/oauth-protected-resource`);
  - servidor de autorização OAuth 2.1 próprio: `/oauth/authorize`, token, **registro dinâmico de cliente** (RFC 7591), **PKCE S256**, `authorization_code` + `refresh_token`, cliente público, escopos `read`/`write`.
  - É o fluxo dos **conectores personalizados** do claude.ai e do Claude Desktop.
- O REA (`analyze_web_bundle`) examinou 19 scripts da página pública: 12 *endpoints* no front (checkout, suporte, parceiros, senha) e **nenhum de MCP**. O MCP deles é todo servidor, e a documentação (`/claude`) fica atrás de login, que não foi acessado. Os nomes das ferramentas deles, portanto, não são públicos.

### 5.2 O que foi implementado no ClipeiAki
- **Servidor de autorização OAuth 2.1** (`web/oauth.py`, *provider* do SDK MCP oficial):
  - registro dinâmico de cliente (só retorno HTTPS ou localhost) e PKCE obrigatório;
  - **tela de consentimento no app** (`/conectar-claude`), que mostra o aplicativo, o domínio de retorno e um alerta quando o domínio não é do Claude;
  - código de uso único (5 min), *access token* de 1 h e *refresh* de 30 dias com rotação, revogação e "Desconectar" na conta;
  - código e tokens guardados só como hash; validação de recurso RFC 8707 ligada.
- Os **tokens pessoais** (`cak_…`) continuam funcionando para o Claude Code.
- **API do Claude no servidor desligada por padrão** (`LIVE_CLAUDE_ENABLED=0`). O caminho antigo continua no código, opcional e testado, mas não é o produto.
- **16 ferramentas MCP:**
  - as 11 pedidas: `list_connected_streamers`, `connect_stream`, `start_monitoring`, `stop_monitoring`, `get_live_status`, `get_live_preview` (imagem), `list_detected_moments`, `get_highlight`, `create_clip`, `approve_clip`, `list_render_jobs`;
  - `get_highlight` devolve **imagens reais** extraídas do buffer e registradas com SHA-256 como "mostradas ao Claude";
  - mais `review_moment` (a decisão do Claude do cliente, validada como a de uma IA: corte de 5–60 s dentro da janela), `get_recent_context`, `check_channel`, `get_render_status` e `remove_stream`;
  - **prompt** `revisar_momentos` com o roteiro de revisão (prioriza os candidatos de maior score).
- Escopos, limite de requisições por token (120 leituras e 20 ações por minuto) e exigência dos Termos vigentes nas ações.
- Como o cliente conecta:
  - **claude.ai / Claude Desktop:** Configurações → Conectores → Adicionar conector personalizado → colar `https://SEU_DOMINIO/mcp` → entrar no ClipeiAki e autorizar;
  - **Claude Code:** `claude mcp add --transport http clipeiaki https://SEU_DOMINIO/mcp` (OAuth) ou com `--header "Authorization: Bearer cak_…"`.

### 5.3 Arquitetura da análise ao vivo (como pedido)
1. O worker (`web.live.agent`) acompanha a transmissão e grava blocos de 10 s.
2. Detectores locais medem picos de áudio, mudança de imagem (quadros-chave com mais de 3 sessões) e palavras de reação (Whisper só nos blocos com pico).
3. Os candidatos são separados com timestamps e o trecho fica no buffer por 15 min.
4. O **Claude do cliente** pede `get_highlight`: até 3 frames e a transcrição da janela. Nada é transmitido continuamente.
5. Ele decide com `review_moment`: relevância, início/fim, título e justificativa.
6. O motor existente renderiza o corte.
7. O usuário recebe o preview e aprova (pelo app ou pelo `approve_clip`).

### 5.4 Testes do MCP (protocolo real, cliente oficial do SDK, via HTTP)

| Teste | Resultado |
|---|---|
| **Fluxo OAuth completo** (`test_oauth_conector_do_claude_fluxo_completo`): descoberta RFC 8414/9728, 401 com `resource_metadata`, registro dinâmico, rejeição de retorno http externo, `/authorize` + PKCE, consentimento (sem login → 401), código de uso único, PKCE errado → 400, token, chamada MCP na conta certa, *refresh* com rotação (o antigo deixa de valer), desconexão (o token cai na hora), recusa → `access_denied`, retorno não registrado → 400, isolamento da desconexão, só hashes no banco | **PASS** |
| **Revisão pelo Claude do cliente com o agente gravando** (`test_mcp_review.py`, SIM): OAuth → prompt → connect → start → candidatos → `get_highlight` com imagens = frames registrados = arquivos servidos no app (SHA-256) → decisão fora da janela recusada → `clip` → corte renderizado com **exatamente** o intervalo e o título decididos → `skip` → nova decisão bloqueada → `approve_clip` → linha do tempo marca "via MCP · Claude" → **0 chamadas de API no servidor** | **PASS** |
| Ferramentas, isolamento, escopos, rate limit, token expirado ou ausente → 401, validade > 365 dias recusada (`test_monitor.py`) | **PASS** |
| Fluxo completo com o agente: connect → start → contexto → momentos → `create_clip` → render → `list_render_jobs` → `approve_clip` → stop; `get_live_preview` = preview da API; `get_highlight` = frames enviados (`test_live.py`) | **PASS** |
| Captura real: `list_connected_streamers` com 3 transmissões gravando (`docs/evidencias/mcp_list_connected_streamers.json`) | **PASS** |
| Claude real (claude.ai) adicionando o conector | **BLOCKED**: precisa de uma URL pública HTTPS, e não houve deploy autorizado |

## 6. Capacidade e custos (detalhes em `docs/CAPACIDADE_E_CUSTOS.md`)

Medido numa VM de 4 vCPU / 15,7 GB. **REAL** = Twitch ao vivo; **FIXTURE** = VOD real tocado como live, sem rede.

| Rodada | Atraso p50 / p95 | Detecção p50 | CPU máquina | Núcleo/transmissão (agente) | Cortes | Recuperação pós-SIGKILL |
|---|---|---|---|---|---|---|
| REAL 3 (kaicenat, gaules, jynxzi) | 3,1 / 15,7 s | 9,1 s | 42% | 0,41 | 3/3 | 3/3 em 24–28 s, sem buracos |
| REAL 10 (10 canais) | **2,2 / 42 s** | 10,7 s | 88% | 0,22 | 10/10 (fila até 247 s) | 10/10 em 22–40 s, sem buracos |
| FIXTURE 3 | 3,0 / 22,7 s | 10,5 s | 47% | 0,39 | 3/3 | 3/3, sem buracos |
| FIXTURE 10 v1 (antes da otimização) | 56 / 115 s | 63 s | 96% | 0,24 | 10/10 (até 290 s) | 10/10, sem buracos |
| FIXTURE 10 v2 | 4,1 / 38 s | 13 s | 90% | 0,26 | 5/10 dentro da janela | 10/10, sem buracos |

- **Banda:** 3,3–3,4 Mbps por transmissão; 34 Mbps para 10; 1,5 GB por transmissão-hora.
- **RAM do agente:** 1,1 GB com 3 transmissões; 2,4–2,8 GB com 10.
- **Disco temporário:** 0,6–2,2 GB, apagado ao encerrar.
- **Minutos analisados:** 24 (REAL 3) e 82 (REAL 10).
- **Tokens e custo de IA para a Eclyss:** **0 / US$ 0.**
- **Otimizações feitas por causa da medição:**
  - Whisper com beam 1, sem condicionar no texto anterior e com bloqueio de n-gramas: de 15,6 s para **2,4 s de CPU por bloco**, sem alucinação;
  - imagem lida só nos quadros-chave acima de 3 sessões: de 1,7 s para 0,2 s;
  - transcrição só nos picos fortes com muitas sessões;
  - render em prioridade baixa.
- **Custo para a Eclyss com 100% da franquia usada:** Creator ≈ **US$ 0,89/mês (10% da receita)**; Studio ≈ **US$ 2,96/mês (23%)**. Premissas: VM de US$ 100/mês por 4 vCPU, câmbio de R$ 5,50, sem a taxa da Cakto (PENDENTE).
- **Atenção:** a capacidade precisa ser provisionada para o pico. Um Studio usando as 10 telas ocupa uma VM de 4 vCPU inteira; o render deve ir para outra máquina.
- **10 simultâneas:** podem ser anunciadas, porque gravação e detecção funcionam em tempo real na mediana sem perda de dados. Condições: o render precisa ser dimensionado à parte, e o anúncio não deve prometer 24/7.

## 7. Jurídico

Páginas públicas, geradas de `web/legal_build.py`. Todas na versão **2026-11-19**, com teste de link e de versão.

| Página | Rota | Cobre |
|---|---|---|
| Termos de Uso | `/termos` | Fornecedor; natureza do serviço e o que existe ou não; conta 18+; planos e franquias (tabela gerada do `plans.yaml`); análise pelo Claude do próprio usuário; Cakto; cancelamento, arrependimento e chargeback; conteúdo; IA pode errar; condutas proibidas e medidas proporcionais; disponibilidade e APIs de terceiros; responsabilidade nos limites do CDC; exclusão; não afiliação; preço alterado só com 30 dias de aviso e na renovação; foro do consumidor |
| Política de Privacidade (LGPD) | `/privacidade` | Tabela dado × finalidade × base legal; conexões OAuth; o que não fazemos; operadores; o Claude do cliente não é operador nosso; transferência; retenção **como o sistema faz**; segurança real e lacunas; incidentes (Res. ANPD 15/2024); direitos e como exercer |
| Cancelamento, Arrependimento e Reembolso | `/cancelamento` | 7 dias com reembolso integral; cancelamento sem multa; reembolso por falha ou cobrança indevida; chargeback com suspensão proporcional; prazos do Dec. 7.962/2013 |
| Conteúdo e Direitos de Terceiros | `/conteudo` | Autoria, imagem, voz, música, jogos; conteúdo proibido; denúncia → análise → medida → contestação |
| Cookies | `/cookies` | Só `vm_session` (essencial) e `lcfg` (localStorage); player da Twitch na página de inspeção |
| Regras do Live Monitor, IA e Integrações | `/regras-live-ia` | Canais próprios ou autorizados; como funciona; o que o Claude vê; limites; limitações conhecidas; conector OAuth e Claude Code |
| Contato, Suporte e Exclusão | `/contato` | Canais (pendentes), prazos, passo a passo de exportação e exclusão |

**Implementado no código para que a política seja verdadeira:**
- aceite versionado no cadastro e reaceite (HTTP 428 em ações contratuais quando a versão muda), guardando só conta, versões, data e contexto;
- exportação em JSON e exclusão da conta (com limite de tentativas de senha; apaga projetos, cortes, transmissões, jobs, uso e arquivos);
- registros de acesso (IP + data/hora de login e cadastro) por 6 meses (Marco Civil, art. 15);
- payload da Cakto minimizado: sem CPF, telefone ou endereço.

**Lacunas declaradas na própria política:** sem criptografia em repouso própria, sem backup, sem expiração automática de vídeos e sem e-mail transacional.

**Revisão de riscos com fontes oficiais:** `docs/RISCOS_JURIDICOS.md`, com 23 itens. Fontes: CDC, Decreto 7.962/2013, LGPD, Marco Civil, Lei 9.610/1998, Código Civil art. 20, Res. ANPD 15/2024, 2/2022 e 19/2024, Guia de cookies da ANPD, Termos da Twitch e da Anthropic.
Nenhum CNPJ, razão social ou dado de pagamento do ViceScale foi reaproveitado; há teste automatizado que verifica isso.

## 8. Segurança — revisão independente (6 achados, todos corrigidos e testados)
1. Uma conta podia ocupar toda a capacidade do servidor.
   - **Correção:** início só com canal ao vivo, 30 inícios por hora por conta e capacidade separada para contas Beta.
2. Ações de corte (web e MCP) não exigiam os Termos vigentes.
   - **Correção:** agora exigem.
3. A exclusão de conta deixava jobs e uso no banco e não limitava tentativas de senha.
   - **Correção:** apaga jobs e uso, limita as tentativas e faz uma segunda limpeza dos arquivos.
4. Franquias de corte e de IA podiam estourar com sessões paralelas.
   - **Correção:** checagem e reserva atômicas.
5. Um rebaixamento de plano não parava as sessões acima do novo limite.
   - **Correção:** o agente agora para essas sessões.
6. Um ROLLBACK podia ser executado fora de transação.
   - **Correção:** ajustado.

Encontrado e corrigido pelos testes:
- A migração do banco tinha uma corrida quando web, worker e agente sobem juntos (o worker morria com "duplicate column"). Agora roda numa transação exclusiva e foi validada com 6 processos simultâneos.
- Um orçamento de IA de US$ 0 encerrava a sessão.
- O contraste do botão primário estava abaixo do mínimo WCAG.

## 9. Relatório PASS / BLOCKED

| Item testado | Resultado | Evidência |
|---|---|---|
| Layout responsivo (375/768/1280/1440) e acessibilidade WCAG 2.1 AA (landing + `/termos`) | **PASS** | `landing_check.js` → `docs/evidencias/landing_check.json` |
| Cards e identificação dos planos (Creator R$ 49,90 / 3; Studio R$ 69,90 / 10), iguais ao backend | **PASS** | `test_planos_publicos_iguais_ao_backend`, `landing_check.js` |
| Ativação de 3 e de 10 telas | **PASS** | `test_ativacao_das_telas_e_bloqueio_da_proxima[creator-3/studio-10]` |
| Bloqueio da 4ª e da 11ª transmissão; corrida; rebaixamento | **PASS** | `test_monitor.py` |
| Sessões de monitoramento e recuperação (SIGKILL, reconexão, buffer contínuo) | **PASS** | `test_live.py` 6/6 + 5 rodadas de carga sem buracos |
| Eventos reais e previews correspondentes (SHA-256 do frame = arquivo servido = imagem do MCP) | **PASS** | `test_live.py`, `test_mcp_review.py` |
| Autenticação e isolamento do MCP (OAuth e token pessoal) | **PASS** | `test_monitor.py`, `test_live.py` |
| Limites da assinatura (franquia mensal, plano inativo, Beta) | **PASS** | `test_monitor.py` |
| Aprovação e renderização dos cortes (web e MCP) | **PASS** | `test_e2e.py` 7/7, `test_mcp_review.py` |
| Links jurídicos e aceite dos Termos (cadastro, reaceite, 428) | **PASS** | `test_aceite_dos_termos_versionado`, `test_paginas_juridicas_publicas_e_links` |
| Regressão do checkout Cakto e do acesso pós-pagamento | **PASS** (webhooks assinados simulados) | `test_cakto_webhooks` |
| Carga com Twitch real (3 e 10) e fixture (3 e 10) | **PASS** | `docs/evidencias/carga_*.json` |
| IDs das ofertas na Cakto | **BLOCKED** | Sem acesso ao painel |
| Compra real na Cakto | **BLOCKED** | Cobrança desligada por decisão (P0) |
| Claude real (claude.ai) conectado ao MCP | **BLOCKED** | Precisa de URL pública HTTPS |
| Deploy de homologação / URL de preview | **BLOCKED** | Não autorizado; **não há URL de preview** |

Comandos para reproduzir:

```bash
pytest -v web/tests/test_monitor.py
```

```bash
VM_TEST_MEDIA=<dir> pytest -v web/tests/test_live.py web/tests/test_e2e.py web/tests/test_mcp_review.py
```

```bash
python -m web.tests.load_live --mode real --streams 10 --minutes 8 --out carga.json
```

## 10. Bloqueios para a venda pública
1. **Gravação da Twitch via streamlink** (risco jurídico J1, P0).
   - Os Termos da Twitch restringem acesso automatizado.
   - Precisa de parecer. A alternativa recomendada é **ingest RTMP próprio** (o streamer adiciona o ClipeiAki como segundo destino no OBS), com OAuth da Twitch para provar a titularidade.
2. **Dados da empresa** (razão social, CNPJ, endereço, e-mail, encarregado) — `PENDENTE_DADO_EMPRESARIAL` em todas as páginas.
3. **E-mail transacional** — sem provedor, não há verificação de e-mail; por isso o plano pago não é liberado e o aceite não é confirmado por e-mail.
4. **Cakto** — IDs das ofertas, fluxo de estorno/arrependimento (cartão e Pix) e um teste de compra real.
5. **Hospedagem** — escolher provedor e assinar o DPA; ver criptografia em repouso e backup; migrar SQLite → Postgres e Blob para mais de uma VM; render em máquina própria para o Studio.
6. **Aprovar as franquias propostas** (60 h / 150 cortes e 200 h / 500 cortes).
7. **Validação jurídica profissional** dos 7 documentos e dos riscos J1–J23, em especial o envio de dados ao Claude do cliente (J6) e o consentimento OAuth (J23).
8. **Deploy de homologação com URL HTTPS** para testar o conector no claude.ai real e rodar o *smoke test* pós-deploy.

**URL de preview:** não há. Nenhum deploy foi autorizado.
