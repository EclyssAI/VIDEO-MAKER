# ClipeiAki (ex-VIDEO-MAKER) — Beta web, Claude Live Agent e Live MCP

Data: 18/11/2026 · Branch: `claude/awesome-noether-nuave7` (a partir de `d56ed53`) · Evidências: `docs/evidencias/`

## 1. Resumo

| Item | Estado |
|---|---|
| Deploy na Vercel | **Não publicado.** Login da CLI não foi aprovado (2 códigos expiraram) e a arquitetura exige decisão de plano pago (§2). |
| URL verificada | Nenhuma URL pública. Tudo foi verificado localmente e em contêiner. |
| Claude Live Agent (gravação, segmentos, transcrição, detecção, cortes, recuperação) | **Funciona com live real da Twitch** (§5). |
| Análise pelo Claude (frames + transcrição → decisão JSON) | **Implementada e testada só com API simulada.** Sem `ANTHROPIC_API_KEY` no ambiente, nenhuma chamada real foi feita. No produto, a análise aparece explicitamente como *desconectada*. |
| ClipeiAki Live MCP (SDK oficial v2) | **Funciona** via HTTP (`/mcp`, token Bearer com escopos) e stdio. 10 ferramentas testadas. |
| Claude Live Monitor (interface) | **Funciona** com dados reais do backend via SSE. Vídeo demonstrativo real gravado. |
| Testes | e2e original 7/7 · Live/MCP simulados 6/6 · Live **real** 1/1 (xQc ao vivo). |
| Renomeação | Interface, título e MCP agora usam **ClipeiAki**. O pacote Python e os caminhos continuam `web/` para não quebrar deploys e testes. |

### O que está no beta e o que é experimental

| Disponível no beta (testado de ponta a ponta) | Experimental / desligado |
|---|---|
| Upload → processamento → preview → aprovação → download | Análise do Claude em lives: código pronto, sem teste real (falta a chave) |
| Gravação contínua de live da Twitch, transcrição, momentos candidatos por áudio/imagem/palavras | Postagem automática nas redes: **não exposta** |
| Corte manual a partir de um candidato, renderizado enquanto a gravação continua | Pagamentos Cakto: desligados (`CAKTO_ENABLED=0`). Exigem verificação de e-mail, que ainda não tem provedor |
| Monitor com timeline, status real do Claude, orçamento, preview, aprovar/baixar | Deploy distribuído (Postgres + Blob + Daemons): só planejado (§2.3) |
| MCP com tokens por usuário e escopos | |

## 2. Vercel

### 2.1 O que foi feito
- A CLI (`vercel` 66.2.0) foi instalada e o login por dispositivo foi solicitado duas vezes (`PXRJ-BFHP` e `RQLQ-KPBP`). Os dois códigos expiraram sem aprovação, então não houve acesso para verificar recursos, permissões ou projetos da conta.
- O pedido de token por formulário seguro foi recusado. Nenhum recurso foi criado e nenhum upgrade foi feito.
- A landing não foi tocada.

### 2.2 Avaliação (fontes oficiais da Vercel, consultadas em 18/11/2026)

| Componente | Vercel Functions | Vercel Daemons (beta) |
|---|---|---|
| Web/API (FastAPI) | Viável. Python é suportado, duração de até 300 s (Hobby) e 800 s (Pro). **Corpo da requisição/resposta limitado a 4,5 MB**, então o upload de vídeo precisa ir direto para o Blob. Não há ffmpeg nem disco compartilhado. | Não recebe tráfego de entrada. |
| Worker de render | Não é viável: duração e CPU insuficientes, sem ffmpeg. | Viável (Dockerfile, sem entrada, disco efêmero). |
| Live Agent (gravação contínua) | **Proibido pelo próprio desenho**: gravação contínua não roda em função HTTP. | Viável no **Pro**. No Hobby, a cota de 5 CPU-h por mês acaba em dias, e todo deploy de produção interrompe os gravadores. |

Riscos decisivos:
- O Hobby é só para uso não comercial.
- **Estourar uma cota no Hobby pausa todos os deploys do time, incluindo a landing.** Isolar o beta exige outro time ou conta.
- O Pro custa aproximadamente **US$ 65–95 por mês** para o beta: US$ 20 de plano + daemons 24/7 ≈ US$ 31–62 + Blob/Functions + Neon, de US$ 0 a 19. A API do Claude é cobrada à parte.

Fontes: [Background workers / Daemons](https://vercel.com/kb/guide/background-workers-on-vercel), [Limites de Functions](https://vercel.com/docs/functions/limitations), [Python runtime](https://vercel.com/docs/functions/runtimes/python), [Vercel Blob client upload](https://vercel.com/docs/vercel-blob/client-upload), [Hobby](https://vercel.com/docs/plans/hobby), [Preços](https://vercel.com/pricing), [Neon](https://neon.com/pricing).

### 2.3 Plano de adaptação distribuída (sem perder dados nem quebrar os testes)
1. **Banco**: camada de compatibilidade SQLite/Postgres em `web/db.py`.
   - `?` passa a ser `%s`.
   - `REAL` vira `DOUBLE PRECISION`, porque o float4 do Postgres corromperia os timestamps dos leases.
   - `AUTOINCREMENT` vira `GENERATED ALWAYS AS IDENTITY`, e `lastrowid` vira `RETURNING id`.
   - `BEGIN IMMEDIATE` vira `BEGIN`, com `SELECT … FOR UPDATE` na cota.
   - A fila usa `FOR UPDATE SKIP LOCKED`.
   - Uma *row factory* aceita índice e nome.
   - Já feito nesta entrega: a coluna `"end"` está entre aspas em todo o SQL, que é palavra reservada no Postgres.
   - Os testes atuais continuam rodando em SQLite. Um job extra roda os mesmos testes contra Postgres.
2. **Arquivos**: os caminhos locais viram chaves de Blob (`source_file`, `video_path`, `thumb_path`, `live_frames.path`).
   - Worker e agente baixam para `/tmp`, processam e sobem o resultado.
   - Os segmentos da live continuam no disco do agente: a lógica de buffer já trata o disco como efêmero.
3. **Upload**: o envio vai direto do navegador para o Blob, com token de cliente de tamanho máximo por plano.
   - O SDK Python não gera esse token, então é preciso uma rota pequena em Node.
   - A medição com ffprobe e a cobrança da cota passam para o worker.
4. **Vídeo**: o preview e o download passam a usar URL assinada do Blob, com Range verificado. Um proxy em função não serve: o limite é 4,5 MB.
5. **Migração de dados**: exportar o SQLite atual e importar no Postgres, copiar `/data` para o Blob e validar com os mesmos testes e2e contra a URL nova.

**Recomendação**:
- Opção híbrida: web na Vercel (com o projeto isolado da landing) e worker + Live Agent numa VM pequena com Docker Compose. Os passos 1–4 continuam necessários.
- Opção mais rápida e mais barata para o beta: o `docker-compose.yml` atual numa VM com HTTPS. Não exige mudança de código. A imagem foi construída e testada nesta e na sessão anterior.

**Decisão necessária (sua)**: (a) Vercel Pro ou um time/conta separado para o beta, (b) uma VM para os processos longos, (c) a criação de Postgres/Blob no Marketplace.

## 3. Claude Live Agent (`web/live/`)

```
streamlink (Twitch) ─▶ ffmpeg segment 10 s ─▶ por bloco: loudness (detect.py do João) · variação de imagem · Whisper base
      │                                         └▶ momento candidato (áudio +9 dB sobre a mediana móvel, palavras de reação, corte visual)
      │                                              └▶ thread Analyzer: até 3 frames JPEG + transcrição da janela + contexto ─▶ Claude API
      │                                                    └▶ JSON validado (decisão, confiança, start_t/end_t na janela, justificativa, eventos)
      │                                                         └▶ corte: concat dos blocos do buffer → fila de render existente (render_live.py do João)
      └── a gravação continua enquanto análise (thread) e render (processo worker) acontecem
```

- **Um canal por sessão.** Uma sessão ativa por usuário e até 2 sessões por processo de agente.
- **Limites por plano** em `config/plans.yaml`: duração máxima, teto de orçamento de IA e número de chamadas.
- **Controle de custo**:
  - Antes de cada chamada, o agente reserva o pior caso (`max_tokens` inteiro) e encerra a sessão se `gasto + reserva > orçamento`.
  - Os frames são reduzidos de 3 para 2 e depois para 1 à medida que o orçamento é consumido.
  - Há um intervalo mínimo entre chamadas e uma fila de no máximo 3 momentos (o resto é descartado com registro).
  - Os gastos são somados de forma atômica no banco.
- **Recuperação**:
  - Cada sessão tem lease com heartbeat. Se o agente cair, outro processo retoma a sessão: mata o gravador órfão (só se o cmdline confirmar que é dele) e reprocessa o que ficou.
  - Um bloco corrompido é registrado e ignorado, sem derrubar a sessão.
  - Um gravador travado é reiniciado. Uma live offline encerra a sessão após 180 s.
- **Retenção**:
  - Os blocos brutos ficam só no buffer (10 min, ou enquanto um momento pendente precisa deles) e são apagados ao encerrar.
  - Ficam guardados apenas os frames efetivamente enviados (com SHA-256), a transcrição e as decisões.
- **Honestidade da análise**:
  - O prompt diz ao modelo que ele só recebe os frames e a fala enviados.
  - A interface mostra exatamente os frames enviados, com o tempo da gravação, o horário UTC e o SHA-256.
  - Não existe "análise contínua de cada frame".

### Correções feitas após a revisão independente (subagentes)
- **Agente**:
  - Erros por bloco e por corte não travam mais a sessão.
  - A sessão encerra de forma definitiva em caso de erro interno.
  - Momentos não ficam mais presos em `analyzing`.
  - O lease é verificado antes de cada escrita, o que evita dois agentes na mesma sessão.
  - Mudanças de estado usam compare-and-set.
  - A linha do bloco e o tempo gravado são gravados na mesma transação.
  - Corte, job e momento são criados numa única transação (sem corte duplicado).
  - A reserva de orçamento usa o pior caso.
  - O frame é extraído com seek na saída, porque os `.ts` começam em PTS 1,4 s e o seek de entrada falhava.
  - A fonte do corte é remuxada para MP4.
- **Segurança**:
  - O proxy confiável deixou de ser `*`.
  - O limite de login passa a valer também por e-mail.
  - O plano pago só vai para e-mail verificado.
  - O corpo das requisições é limitado a 256 KB (exceto o upload).
  - scrypt e ffprobe rodam fora do event loop.
  - O streamlink tem cache, semáforo e limite por usuário.
  - Há limite de renders na fila e de conexões SSE por usuário.
  - Números são validados (NaN/inf viram 400).
  - Textos de legenda têm quebras de linha removidas.
  - O gravador usa `shlex.quote` e validação explícita, sem `assert`.

## 4. ClipeiAki Live MCP (`web/mcp_server.py`)
- **SDK**: oficial `mcp` 2.3 (`MCPServer`).
  - Por HTTP: `<PUBLIC_URL>/mcp`, sem estado, com respostas JSON e metadados OAuth do recurso em `/.well-known/oauth-protected-resource/mcp`.
  - Por stdio: `CLIPEIAKI_TOKEN=cak_... python -m web.mcp_server`.
- **Ferramentas**: `check_channel`, `list_sessions`, `get_session`, `start_monitoring`, `stop_monitoring`, `get_recent_context`, `list_moments`, `create_clip`, `get_render_status`, `list_clips`.
- **Autenticação**: token pessoal criado em *Conta → ClipeiAki Live MCP*. O banco guarda só o SHA-256 e a revogação vale na hora.
- **Escopos**: `live:read`, `live:control`, `clips:read`, `clips:write`.
- **Isolamento**: todas as consultas são filtradas pelo dono do token.
- O MCP chama as mesmas funções da API web (`web/live/service.py`): não há lógica de captura ou edição duplicada.
- A automação contínua **não depende** de uma sessão do Claude Code: é o backend (Live Agent) que chama a Claude API.
- Para conectar no Claude Code:

```bash
claude mcp add --transport http clipeiaki https://SEU_DOMINIO/mcp --header "Authorization: Bearer cak_SEU_TOKEN"
```

## 5. Evidências de teste (separadas por tipo)

### REAL (nada simulado)

| Teste | Resultado |
|---|---|
| `test_live_real.py`, xQc ao vivo, 4 min (`live_real_metricas.json`) | **PASS** |
| Sessão manual com Kai Cenat ao vivo, 12 min (antes da otimização) | Funcionou. Ver o achado de capacidade abaixo |
| Demo `demo_live_monitor_REAL_twitch.mp4` (xQc, Claude desconectado) | Timeline real, candidato → "Criar corte" → preview 1080×1920 tocando |
| `test_e2e.py` (upload, isolamento, limites, queda do worker, Cakto) | **7/7 PASS** |

Detalhes do teste com xQc:
- 24 blocos (240 s), contínuos, sem buracos.
- Atraso de processamento: p50 **3,2 s**, máximo **7,4 s**.
- 6 candidatos, detectados **4–12 s** após o evento.
- Corte renderizado em **28,6 s** com a gravação rodando.
- Buffer apagado ao encerrar.
- Claude mostrado como desconectado e nenhum frame enviado.

Achado de capacidade na sessão com Kai Cenat: com Whisper `small` e a suíte de testes disputando os 4 vCPUs, o atraso chegou a **211 s**. Isso foi corrigido com Whisper `base` para a live e um modo de recuperação que pula a transcrição de blocos sem pico de áudio quando há fila.

### SIMULADO (vídeo real de gameplay tocado como live + API Claude falsa local, `web/tests/fake_claude.py`)

`test_live.py`: **6/6 PASS**.

| Teste | O que prova |
|---|---|
| Monitoramento, análise e corte durante a gravação | <ul><li>SSE com ids crescentes</li><li>**frame exibido = frame registrado = bytes recebidos pela "API"** (SHA-256)</li><li>frames e decisão dentro da janela</li><li>corte com a duração decidida (±0,6 s)</li><li>blocos gravados durante o render</li><li>timestamps contínuos</li><li>chave nunca chega ao navegador</li></ul> |
| Falha do Claude e reconexão do stream | Erro 500 → estado "erro" → recupera; gravador morto → `disconnected` → `reconnected`, linha do tempo contínua |
| Reinício do agente | SIGKILL no agente → sessão retomada, gravador órfão encerrado, gravação continua |
| Orçamento | Redução 3→2 frames conforme o gasto e encerramento por `budget` sem passar do limite |
| Isolamento | <ul><li>Outro usuário recebe 404 em sessão, contexto, frame, SSE, stop e corte</li><li>Token sem escopo é recusado</li><li>Token revogado e acesso sem token dão 401</li></ul> |
| MCP | Iniciar, ler contexto, listar momentos, criar corte por intervalo, acompanhar render, listar cortes, parar — via HTTP real com token |

A demo `demo_live_monitor_SIMULADO_claude_falso.mp4`:
- A interface mostra "Conectado **SIMULADO-sem-claude**", e as justificativas vêm marcadas `[SIMULADO]`.
- A verificação no navegador confirmou que o frame exibido tem o mesmo SHA-256 dos bytes enviados.
- Latência simulada evento→corte pronto: **45,5 s** (detecção + 8 s pós-evento + render 27 s). A latência real do Claude não está incluída.

### NÃO EXECUTADO
- Análise real com Claude (sem `ANTHROPIC_API_KEY`). Por isso, a latência evento → análise → corte com Claude real **não foi medida**.
- Deploy e smoke test em URL pública (sem acesso à Vercel).
- Postgres/Blob (só planejado).
- Compra real na Cakto.

## 6. Custos observados
- **Claude API**: US$ 0, porque nenhuma chamada real foi feita.
  - Estimativa por chamada (3 frames ≈ 2,5 mil tokens de entrada + até 3 mil de saída no Opus 5.5): US$ 0,02–0,07. A reserva de pior caso é US$ 0,07.
  - Com o orçamento padrão do Beta (US$ 0,50), a sessão encerra sozinha antes de passar disso.
- **Infraestrutura**: US$ 0 (tudo rodou nesta máquina). Para a Vercel, ver §2.2.

## 7. Bloqueios restantes
1. **Vercel**: aprovar o login da CLI (`vercel login`) e decidir o plano e o isolamento da landing (§2.3).
2. **Claude real**: definir `ANTHROPIC_API_KEY` como variável de ambiente do servidor (no ambiente de nuvem "ClipeiAKI": Editar → variáveis; ela é visível para quem usa o ambiente). Depois, rodar:

   ```bash
   LIVE_REAL=1 pytest web/tests/test_live_real.py
   ```

   Esse teste passa a exigir análises reais e registra latência e custo.
3. **Verificação de e-mail**: precisa de um provedor de e-mail. Sem isso, os planos pagos não são aplicados (proteção contra sequestro de assinatura).
4. **Riscos aceitos no beta**:
   - Tokens de API sem expiração.
   - Duração do upload confiando no metadado do contêiner.
   - SSE consultando o banco a cada segundo (precisa de pooling no Postgres).
