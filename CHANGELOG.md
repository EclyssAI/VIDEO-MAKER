# Changelog — ClipeiAki
Versionamento semântico (MAJOR.MINOR.PATCH). Versão atual em `VERSION`.

## [0.7.0] — 2026-11-19 — Live Monitor multi-transmissão, MCP completo, landing e documentos jurídicos
- Live Monitor: transmissões conectadas em slots do plano (Creator 3, Creator Studio 10, Beta 1), limite aplicado no backend em
  transação (sem corrida), bloqueio da 4ª/11ª, rebaixamento de plano respeitado, capacidade total do servidor (`LIVE_CAPACITY_TOTAL`).
- Grade de 3/10 telas com preview real (último frame gravado, extraído na mesma decodificação da detecção), status, duração,
  candidatos, cortes e ações iniciar/pausar/remover/inspecionar; franquia mensal de horas e cortes contada bloco a bloco.
- Live Agent: Whisper ~6x mais leve (beam 1, sem condicionamento, bloqueio de n-gramas), transcrição por evento, imagem por
  quadros-chave acima de 3 sessões, banda medida por bloco; correção: orçamento de IA US$ 0 não encerra mais a sessão.
- MCP: 15 ferramentas (list_connected_streamers, connect_stream, start/stop_monitoring, get_live_status, get_live_preview com
  imagem, list_detected_moments, get_highlight com evidências, create_clip, approve_clip, list_render_jobs…), limite de
  requisições por token, tokens com validade.
- Jurídico: 7 páginas públicas, aceite versionado (cadastro e reaceite com HTTP 428), exportação e exclusão de dados,
  registros de acesso por 6 meses, payload da Cakto minimizado. Revisão de riscos em `docs/RISCOS_JURIDICOS.md`.
- Landing comercial servida em `/` para visitantes (gerada de `web/site_src` + `config/plans.yaml` por `python -m web.site_build`).

## [0.6.0] — 2026-11-18 — Produção em lote (stack)
- `capture/harvest.py`, `capture/stack.py` (plan/prepare/apply), `capture/deliver.py`.
- Detecção automática de webcam/rosto com YuNet (OpenCV), modelo em template/models/.
- Remoção de trechos com fala repetida, `trim_bottom` para cortar legenda gravada da live, legendas sem sobreposição.

## [0.5.0] — 2026-11-18 — Padrão dos clipadores grandes
- Legenda karaokê (palavra falada em amarelo/maior).
- `zoom` por trecho (ritmo visual), cold open no clímax, cortes secos de silêncio.
- Regras na /viralizei: checagem de frame 0, silêncio, duração 61–90 s.

## [0.4.0] — 2026-11-18 — Compilações monetizáveis + regras do canal
- Template: mascote encosta na barra inferior.
- Legendas: apenas tradução da fala (sem comentários nossos).
- Títulos: `screen_title` (tela, molde gringo) separado de `title` (post, com pergunta de engajamento); skill hook-writer-sms instalada.
- Modo compilação (`_compilation` no copy.json): vários trechos → um vídeo > 60 s (TikTok Creator Rewards).
- `focus` por trecho para centralizar o streamer em layout sem webcam.

## [0.3.1] — 2026-11-18 — Primeiro clip real
- Legendas com quebra em 2 linhas + ajuste automático de tamanho (não cortam mais na borda).
- Áudio normalizado para -14 LUFS / pico -1,5 dBFS (padrão TikTok/Reels/Shorts).
- Saída fixa em 30 fps (antes herdava 25 fps da imagem de fundo).
- Captação: YouTube e Reddit bloqueiam o IP do servidor (exigem cookies); clips da Twitch funcionam.

## [0.3.0] — 2026-11-17 — Esteira completa
- `esteira.py`: um comando por etapa (scrap, live, add, cut, render, approve, post, status).
- `capture/scrap.py`: clone gratuito do ViceScrap + ViceRepost (yt-dlp, ranking por outlier de views, `logs/seen.json` evita repetir).
- Detecção genérica: vídeo longo/live → vários cortes por pico de áudio; vídeo curto → corte inteiro.
- Render aceita fonte vertical (TikTok/Reels) no quadro único.
- `publish/`: postagem via APIs oficiais grátis — YouTube Shorts, Instagram Reels (upload resumível), TikTok (Content Posting API) + fila com horários de pico (`publish/scheduler.py`).
- REA (morluto/rea) registrado como MCP em `.mcp.json`; usado para mapear o ViceScale (só páginas públicas).
- Skill `viral-tiktok-hooks` instalada; `/viralizei` ganhou rotação anti-repetição de ângulos de título.

## [0.2.0] — 2026-11-17 — Cortes de lives
- Template ClipeiAki (frame com/sem webcam, fundo, logo, mascote) em `template/assets/`.
- `live/cycle.py`: gravação em ciclos de 30 min na madrugada (streamlink), sem buracos entre ciclos.
- `live/detect.py`: gritos/sustos/reações por loudness + transcrição local (faster-whisper) só dos trechos.
- `live/render_live.py`: jogo no quadro maior, streamer no menor, título, legenda, punch-in zoom, SFX (whoosh/impacto).
- Skills: find-skills, superpowers (obra), sound.

## [0.1.0] — 2026-11-17 — Scaffold
- Estrutura de pastas, `PLANO.md`, pipeline inicial (prepare/render), skill `/viralizei` e checklist de score.
