# ClipeiAki — automação de clips GTA
1. Cole links em `input/queue.txt` (`link | crédito | meme|curiosidade`) — saída do ViceScrap.
2. `python pipeline/run.py prepare` → baixa + transcreve (local, grátis).
3. No Claude: `/viralizei` traduz (PT-BR) e gera `work/<id>/edit.json` de todos os vídeos em lote.
4. `python pipeline/run.py render` → `output/<data>_<slug>/{video.mp4, descricao.txt, meta.json}`.
Requisitos: ffmpeg, `pip install yt-dlp faster-whisper pyyaml`. Plano completo em `PLANO.md`.
Nota: renderizador atual = ffmpeg/libass; adaptador Raea pendente (ver PLANO.md §3).
