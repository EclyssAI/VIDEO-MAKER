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
