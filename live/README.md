# Cortes de lives (madrugada)
1. `config/live.yaml`: streamers (url, idioma, posição da webcam ou null). Medir webcam: `python live/cam_probe.py <url>`.
2. `python live/setup_assets.py` (uma vez: máscaras + SFX).
3. `nohup python live/cycle.py > logs/cycle.log 2>&1 &` (`--always` ignora o horário da madrugada).
4. A cada 30 min: `BATCH_READY` → Claude escreve `copy.json` (títulos/legendas PT-BR) → `output/live/<batch>/NN_slug/{video.mp4,thumb.jpg,descricao.txt,meta.json}`.
5. Você aprova: `python esteira.py approve <lote> 1 3` → agenda e posta em TikTok/Reels/Shorts (publish/README.md).
Layout: jogo no quadro maior, streamer no menor quando há webcam; sem webcam = jogo no quadro único.
