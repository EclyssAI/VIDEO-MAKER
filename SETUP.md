# Recomeçar em um ambiente novo
```bash
git clone <repo> && cd VIDEO-MAKER && git checkout claude/clipeiaki-gta-automation-e1xdnu
pip install -r requirements.txt        # + ffmpeg (com libass) instalado no sistema
python live/setup_assets.py            # regenera máscaras e SFX (já versionados; só se mudar o layout)
```
- Skills do Claude já vêm no repo em `.claude/skills/` (viralizei, find-skills, superpowers, sound, viral-tiktok-hooks).
- REA: `npx -y rea-agents@6.9.0 setup` (Node ≥ 22.23.4) — já registrado em `.mcp.json`.
- Credenciais (NÃO versionadas): `config/secrets/` → `youtube_token.json`, `instagram.json`, `tiktok.json`, `cookies.txt` (ver `publish/README.md`).
- Preencher: `config/sources.yaml` (perfis gringos) e `config/live.yaml` (streamers + posição da webcam via `python live/cam_probe.py <url>`).
- Rede do ambiente precisa liberar: twitch/kick (lives), tiktok/instagram/youtube (captura), graph.facebook.com, rupload.facebook.com, open.tiktokapis.com, googleapis.com (postagem), huggingface.co (modelo whisper).

## Fluxo diário
1. `python esteira.py scrap` e/ou `python esteira.py live` (madrugada) ou `python esteira.py add <link>`
2. Claude + `/viralizei`: lê `work/batch/<lote>/for_claude.txt`, escreve `copy.json`
3. `python esteira.py render <lote>` → revisar `output/<lote>/`
4. `python esteira.py approve <lote> 1 3` → posta sozinho nos horários de pico
