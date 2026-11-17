# Changelog — ClipeiAki
Versionamento semântico (MAJOR.MINOR.PATCH). Versão atual em `VERSION`.

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
