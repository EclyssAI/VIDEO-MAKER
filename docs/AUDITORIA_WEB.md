# VIDEO-MAKER — Auditoria da entrega do João e conversão para SaaS Web

Data: 18/11/2026 · Branch: `claude/awesome-noether-nuave7` · Evidências em `docs/evidencias/`

## 1. Origem da entrega auditada

| Item | Valor |
|---|---|
| Repositório | `eclyssai-glitch/VIDEO-MAKER` (é o mesmo que `EclyssAI/VIDEO-MAKER`: `git ls-remote` dos dois devolve o mesmo HEAD) |
| Branch de entrega | `claude/clipeiaki-gta-automation-e1xdnu` (única branch remota; sem releases, tags ou PRs) |
| Commit final | `e4dfbd7` — "Créditos de todos os streamers nas compilações" — 18/11/2026 02:38 UTC |
| Versão declarada | `VERSION` = 0.6.0 (CHANGELOG 0.1.0 → 0.6.0, de 17/11 a 18/11) |
| "Versão antiga" do repositório | É o histórico da mesma branch (`79e5370` v0.1 scaffold → `e4dfbd7`). A branch de trabalho desta sessão começou em `e4dfbd7`, então a entrega final e o ponto de partida são o mesmo commit. |

**Achado importante — não existe aplicativo instalável no repositório.** Não há instalador, PyInstaller, Electron,
`setup.py` nem build de desktop em nenhuma branch, tag ou release acessível. Os outros repositórios da organização
(`VEREDA`, `KORIUMBack`, `The-FORGE`) não contêm VIDEO-MAKER, ClipeiAki nem Cakto (busca de código sem resultados).
O que o João entregou é uma **esteira de linha de comando em Python** operada por uma sessão do Claude Code. Se existe
um instalador fora do GitHub, ele não foi entregue a esta auditoria e precisa ser enviado para comparação.

### Arquitetura da entrega (o que é cada parte)

| Camada | Arquivos | Observação |
|---|---|---|
| Interface | nenhuma | Só CLI (`esteira.py`) + Claude Code lendo `for_claude.txt` |
| Motor | `live/detect.py` (loudness + picos + faster-whisper), `live/render_live.py` (template ffmpeg/libass 9:16), `capture/stack.py` (YuNet webcam, compilações) | Núcleo reaproveitado integralmente |
| Captura | `capture/scrap.py`, `capture/harvest.py`, `live/cycle.py` (streamlink) | yt-dlp / streamlink |
| Publicação | `publish/{youtube,instagram,tiktok,scheduler}.py` | APIs oficiais, credenciais em `config/secrets/` |
| API / banco | nenhum | Estado em JSON (`logs/queue.json`, `pending.json`, `copy.json`) |
| Dependências locais | ffmpeg com libass, Python 3, modelo Whisper "small" (HuggingFace), fonte Inter, YuNet ONNX | |
| Integrações | Claude (manual, via sessão), YouTube/Instagram/TikTok APIs, Twitch/Kick | Cakto: **inexistente** |
| Skills / MCP | viralizei, find-skills, superpowers, sound, viral-tiktok-hooks, hook-writer-sms; MCP REA (`.mcp.json`) | Usados no desenvolvimento; nenhum é necessário em runtime |

## 2. Matriz de funcionalidades verificadas (testes reais, nesta máquina)

| Funcionalidade | Status | Evidência reproduzível |
|---|---|---|
| Download de clip/VOD Twitch (yt-dlp) | **PASS** | `yt-dlp` baixou clip de 45 s (1920×1080) e trecho de 240 s de VOD |
| Varredura de clips Twitch (`capture/harvest.py`) | **FAIL** | `python capture/harvest.py ramee koil` → "clips listados: 0". Com `range=7d` o yt-dlp devolve 0 itens até para xqc; com `range=all` funciona. O filtro de 7 dias quebrou. |
| Scrap YouTube/Instagram/TikTok (`capture/scrap.py`) | **FAIL / NÃO TESTADO** | YouTube: "Sign in to confirm you're not a bot" sem cookies. `config/sources.yaml` só tem perfis de exemplo (`PERFIL_GTA`). |
| Gravação de live (streamlink) | **PASS** | 20 s gravados de `twitch.tv/xqc` → `.ts` de 21 MB, 19,99 s |
| Ciclo de madrugada (`live/cycle.py`) | **NÃO TESTADO** | `config/live.yaml` só tem streamers de exemplo; processamento roda em thread daemon sem retomada |
| Detecção de momentos | **PARCIAL** | Clip curto (≤59 s) → corte inteiro OK. VOD real de 4 min: limiar fixo de 14 dB → **0 cortes**; 10 dB → 2; 8 dB → 4 |
| Transcrição (faster-whisper) | **PASS** | 24 palavras com tempo no clip de 45 s, 14 s incluindo download do modelo |
| Detecção de webcam (YuNet) | **PARCIAL** | Clip: webcam localizada corretamente (`auditoria_webcam_yunet.jpg`). VOD com chat: recorte incluiu parte do chat (`e2e_frames_renderizados.jpg`, 2º quadro) |
| Render 9:16 + legenda karaokê | **PASS** | 1080×1920, 30 fps, AAC; ~54 s para 45 s de vídeo em 4 vCPU (`auditoria_render_motor_joao.jpg`) |
| Normalização de áudio −14 LUFS | **PARCIAL** | Medido: −16,4 LUFS integrado (loudnorm de 1 passada) |
| Render com `broll.enabled: false` + webcam | **FAIL** | ffmpeg: "Input frame sizes do not match (1014x800 vs 1014x801)". Bug latente: a config do João sempre usa broll ligado |
| Integração / autonomia do Claude | **FAIL (autonomia)** | Títulos e traduções dependem de uma sessão do Claude Code escrevendo `copy.json`. Sem ela, `render_live.py` pula cortes em inglês ("aguardando tradução") |
| Agendador (`publish/scheduler.py`) | **PARCIAL** | Aprovar o item 1 e depois o 2 do mesmo lote marca o 1 como "reprovado", mas ele continua na fila e seria postado |
| Postagem YouTube / Instagram / TikTok | **NÃO TESTADO** | Sem credenciais. TikTok vem com `PUBLIC_TO_EVERYONE`, que a API recusa em app não auditado (o próprio README do João diz SELF_ONLY) |
| Filas e recuperação de falhas (versão do João) | **FAIL** | Fila em JSON sem lock nem retentativa; se o processo morre, o lote em processamento se perde |
| Credenciais e segurança | **PARCIAL** | Nenhum segredo no histórico do git (varredura de `git log -p`). Segredos em arquivos locais em texto puro. `live/cam_probe.py` usa `shell=True` com URL (injeção se fosse exposto — não é exposto no web) |
| Instalação e dependências | **PASS (CLI)** | `pip install -r requirements.txt` + ffmpeg OK. Não há instalador. MCP REA (Node ≥ 22.23.4) não testado |
| Pipeline v0.1 (`pipeline/`) | **NÃO TESTADO** | Substituído pelo `live/` desde a v0.2 |

## 3. Arquitetura desktop → web

```
Navegador (SPA web/static)            Servidor web (FastAPI, web/app.py)          Worker (python -m web.worker)
  login / upload / estúdio  ──HTTPS──▶  auth, projetos, cortes, limites,   ──SQLite──▶  claim com lease + heartbeat
  preview <video> / download             upload em streaming, webhook Cakto   (WAL)     analyze: detect.py + whisper + YuNet
                                          arquivos por cliente em /data/users/<id>        copy: Claude API (opcional)
                                                                                          render: render_live.render (João)
```

* **Processamento contínuo fora do navegador e fora de funções temporárias**: o worker é um processo longo na mesma VM
  do servidor web, com volume persistente. Gravação de lives 24/7 **não** foi exposta no web (ver §7).
* **Estados persistentes**: `projects.status` (uploading → queued → processing → rendering → done/failed),
  `clips.status` (queued → rendering → ready → approved/discarded/failed), `jobs` com progresso e etapa.
* **Recuperação**: job `running` cujo lease expira volta à fila (até 3 tentativas); análise é idempotente (apaga cortes da tentativa anterior).

## 4. Componentes reutilizados (sem alteração)

`live/detect.py` (`loudness`, `peaks`, mesmo modelo Whisper), `live/render_live.py` (`render`, template, karaokê,
layout com webcam, SFX, zoom, loudnorm), `capture/stack.py` (`layout` com YuNet), `template/` (fundo, molduras,
máscaras, SFX, modelos), `config/live.yaml` (parâmetros de detecção/layout). **Nenhum arquivo do João foi modificado.**

Mudanças de comportamento feitas no adaptador `web/engine.py`, cada uma com justificativa:

1. Limiar adaptativo 14 → 10 → 8 → 6 dB (o fixo deu 0 cortes num VOD real).
2. Idioma detectado devolvido (o `detect.transcribe` descarta) — mesmo modelo em cache.
3. Pacote de assets por cliente: logo e mascote "ClipeiAki" são a marca do canal; clientes recebem moldura neutra
   com o próprio `@handle` no rodapé e legenda centralizada.
4. Plano Creator sem SFX/zoom mantendo o `zoompan` no grafo com janela vazia — contorna o bug latente do render.
5. Títulos/legendas: Claude API (SDK oficial, saída JSON estruturada) quando `ANTHROPIC_API_KEY` existe; sem chave,
   título padrão editável + legenda no idioma original (o fluxo nunca trava esperando uma sessão manual).

## 5. Alterações implementadas (novas, isoladas em `web/` + arquivos de deploy)

| Requisito | Implementação |
|---|---|
| Autenticação | e-mail + senha (scrypt), sessão opaca em cookie HttpOnly/SameSite=Lax/Secure, limite de tentativas, convite opcional |
| Isolamento por cliente | toda consulta filtra `user_id`; arquivos em `/data/users/<id>/`; caminho resolvido e checado contra o diretório do dono |
| API de projetos e jobs | `/api/projects`, `/api/clips/*`, `/api/library`, `/api/billing`, `/healthz` |
| Upload | PUT em streaming direto para disco, limite por plano, validação com ffprobe (vídeo + áudio) |
| Processamento assíncrono | worker separado, fila SQLite com lease, heartbeat e 3 tentativas |
| Progresso | etapa + % por job, polling a cada 3 s na interface |
| Biblioteca, preview e download | `<video>` com HTTP Range (206), download só após aprovação, texto do post para copiar |
| Limites por plano | `config/plans.yaml`: projetos/mês, minutos/mês, duração e tamanho máximos, cortes por vídeo, efeitos premium; falhas não consomem cota; máx. 2 projetos simultâneos |
| Segurança HTTP | CSRF por header obrigatório, CSP restritiva (sem inline), X-Frame-Options DENY, no-store na API |
| Interface | Painel, Novo projeto, Estúdio de cortes (aprovar, editar título/legendas e re-renderizar, descartar), Biblioteca, Conta e plano; responsiva com tab bar no celular |
| Publicações | **não exposta**: a postagem do João é de um único operador com credenciais locais; não há OAuth por cliente |
| Deploy | `Dockerfile` (web e worker na mesma imagem), `docker-compose.yml` com volume, `.env.example` |

## 6. Testes ponta a ponta (reais, sem mocks)

`VM_TEST_MEDIA=<dir> pytest -v web/tests/test_e2e.py` sobe servidor e worker como processos e usa vídeos reais da
Twitch. Resultado: **7 passed em 336 s** (`docs/evidencias/e2e_pytest.log`).

| Teste | O que prova |
|---|---|
| fluxo login → upload → processamento → preview → aprovação → download | MP4 baixado com 1080×1920 + áudio, duração = corte; download bloqueado (403) antes de aprovar; Range 206 |
| edição re-renderiza | novo título aparece no vídeo (`e2e_frames_renderizados.jpg`, 1º quadro, com `@anaclips`) |
| dois clientes isolados | cliente B recebe 404 em todos os endpoints do projeto/corte de A; diretórios separados; B processa VOD de 4 min → 2 cortes |
| erros e segurança | arquivo falso, vídeo sem áudio, extensão inválida, sem CSRF (403), sem sessão (401), força bruta (429), CSP |
| limites do plano | vídeo de 16 min recusado (Beta = 15 min); 4º projeto do mês recusado (402) |
| worker morto com SIGKILL no meio | job fica `running`, lease expira, novo worker retoma (tentativa 2) e conclui todos os cortes |
| Cakto | assinatura inválida 401 (HMAC e secret no corpo), liberação Creator, idempotência, upgrade para Studio (HMAC), renovação do plano menor não rebaixa, render premium, cancelamento mantém até o fim do período, reembolso corta, compra antes do cadastro, vencimento, oferta desconhecida ignorada |

Teste no navegador real (`web/tests/ui_flow.js`, Playwright/Chromium): cadastro → upload pelo seletor de arquivo →
corte pronto em 64 s → `<video>` reporta 1080×1920 / 45,0 s → aprovar → download de 18,6 MB → biblioteca. Zero erros de
JavaScript. O mesmo script serve de smoke test pós-deploy (`BASE=<url> MEDIA=<video> node web/tests/ui_flow.js`).

**Contêiner**: a imagem do `Dockerfile` foi construída e executada (web e worker em contêineres separados, volume
compartilhado, `HF_HUB_OFFLINE=1` para provar que o modelo está embutido). O mesmo teste de navegador passou contra o
contêiner: corte pronto em 58 s, download de 18,6 MB, sem erros. (No build desta sessão foi injetado o CA do proxy da
sandbox por um Dockerfile auxiliar fora do repositório; o `Dockerfile` versionado não tem nada disso.)

## 7. Publicação

**Não publicado.** Não há projeto/credencial de hospedagem utilizável nesta sessão: o token GCP do ambiente é recusado
(`UNAUTHENTICATED`), não há projeto de destino nem chaves de Vercel/Fly/Railway/Render, e não foram usadas credenciais
de nuvem de origem desconhecida. Também não foi contratado nenhum serviço. A landing e os serviços do João não foram tocados.

O que é necessário para publicar (≈30 min com acesso):
1. Uma VM com 4 vCPU / 8 GB / disco persistente (render de 45 s leva ~55 s em 4 vCPU), Docker e HTTPS na frente (Caddy/Nginx).
2. `cp .env.example .env`, `COOKIE_SECURE=1`, `BETA_SIGNUP=1` e `SIGNUP_INVITE_CODE` para beta fechado.
3. `docker compose up -d --build` e smoke test: `/healthz`, cadastro, upload do vídeo de teste, download.

A imagem Docker foi construída e testada localmente (ver §6).

## 8. Status da integração Cakto

* Não existia nenhuma integração Cakto no código do João; foi implementada em `web/billing.py`.
* Webhook `/api/webhooks/cakto`: HMAC `X-Cakto-Signature` (tolerância de 5 min) ou `secret` no corpo, comparação em tempo
  constante; idempotente por `data.id`+evento; plano decidido por `offer.id`.
* **Desligada por padrão** (`CAKTO_ENABLED=0`): sem checkout na interface ("Assinaturas abrem em breve") e webhook responde 503.
* Pendências antes de cobrar: (a) os `offer.id` reais dos dois planos; (b) confirmar se o painel da Cakto envia o
  header HMAC ou só o `secret`; (c) a Cakto não documenta data de próxima cobrança — o código libera 32 dias por
  aprovação/renovação; (d) confirmar os limites de `config/plans.yaml` com a landing; (e) um teste com compra real de
  valor mínimo em sandbox.

## 9. Veredito

**NO-GO para lançamento público com cobrança em 19/11.**
**GO para beta/demonstração fechado** (convite, plano Beta gratuito, cobrança desligada), assim que houver uma VM.

Motivos do NO-GO:
1. Não há hospedagem disponível; nada foi publicado nem passou por smoke test em URL pública.
2. Títulos/tradução automáticos via Claude API não foram testados contra a API (sem chave no ambiente): hoje o cliente recebe título padrão e legenda no idioma original.
3. Cakto sem as ofertas reais e sem teste de compra real.
4. Captura automática (harvest/scrap) e publicação nas redes não funcionam ou não foram testadas — ficaram fora do produto web.
5. Qualidade de detecção depende do conteúdo (limiar por áudio; webcam com chat pode ser recortada errado).
6. Capacidade: um worker processa um job por vez; ~1,2× o tempo real por corte em 4 vCPU.

O que está pronto e comprovado: fluxo completo do cliente com processamento real, isolamento entre clientes, limites
por plano, recuperação após queda do worker e webhook Cakto testado com eventos simulados assinados.
