# ClipeiAki — Plano de automação (GTA clips)

> **Status (v0.3.0):** Fases A e B implementadas; Fase C (postagem automática) implementada, aguardando credenciais. Uso atual: `README.md` / `SETUP.md`. Histórico: `CHANGELOG.md`.
> Mudanças vs. plano original: ViceScrap → `capture/scrap.py` (yt-dlp); Raea → render ffmpeg/libass; postagem via APIs oficiais (`publish/`).

## 1. Pipeline (1 comando, 1 chat, pouco token)
```
ViceScrap (descoberta) → download → transcrição → tradução PT-BR → /viralizei (título, hook, descrição, hashtags)
   → template ClipeiAki (Raea) → render 9:16 → output/<id>/{video.mp4, meta.json, descricao.txt}
```
Princípio de economia de tokens: **scripts determinísticos fazem 95% do trabalho**
(ffmpeg, whisper local, Raea CLI). O Claude só entra em 2 pontos de baixo custo:
tradução/copy (1 chamada em lote para N vídeos) e decisão de corte/hook.

## 2. Estrutura de pastas
```
VIDEO-MAKER/
├── PLANO.md
├── config/            channel.yaml (nome, cores, fonte, hashtags), sources.yaml (páginas gringas)
├── template/          template ClipeiAki (composição Raea: intro, legenda, watermark, outro)
├── research/          modelos virais estudados (formatos, títulos, ganchos)
├── pipeline/          scripts: discover.py, download.py, transcribe.py, translate.py, render.py, run.py
├── input/             raw/ (baixados)  queue.json (candidatos do ViceScrap)
├── work/              temporários (legendas .srt, cortes)
├── output/            <data>_<slug>/video.mp4 + meta.json (título, descrição, tags) + descricao.txt
├── .claude/skills/    viralizei/SKILL.md  (+ find-skills instalada)
└── logs/              posted.json (evita repostar), métricas
```

## 3. Stack proposta
| Etapa | Ferramenta | Observação |
|---|---|---|
| Achar skills | `npx skills find` (vercel-labs/find-skills) | instalar skills de vídeo/legenda/hook |
| Descoberta | **ViceScrap** | ⚠ não encontrei publicamente — preciso de acesso/formato de saída |
| Download | yt-dlp | |
| Transcrição | faster-whisper (local, grátis) | |
| Tradução | Claude (lote) | gíria gamer PT-BR |
| Edição/render | **Raea** (CLI `raea`, SDK TypeScript, composições) + ffmpeg (instalado) | confirmar repo shinyobjectz/raea |
| Postagem | YouTube Data API / TikTok / Reels (fase 2) | início manual ou agendador |

## 4. Skill `/viralizei` (aplicada a TODO vídeo)
Checklist automático, baseado em padrões observados em clips de GTA:
1. **Gancho 0–2 s**: começar 1 beat antes do momento-chave; texto-gancho na tela.
2. **Estrutura**: gatilho → contexto curto → escalada → reação → payoff → **cortar logo após**.
3. **Duração**: meme 10–20 s; curiosidade 25–45 s; nunca > 60 s.
4. **Legenda animada** palavra-a-palavra, sempre PT-BR, legível sem som.
5. **Título**: curiosidade/choque + palavra-chave (GTA 6, GTA RP...) ≤ 60 caracteres; 3 variações A/B.
6. **Descrição**: 1ª linha = gancho, CTA ("segue o ClipeiAki"), hashtags (#gta6 #gta #shorts), crédito.
7. **Loop**: final que emenda no início (rewatch).
8. **Postagem**: horários de pico, 1–3 posts/dia, qualidade > volume; pergunta nos comentários.
9. Score final (0–100) via checklist; abaixo de 70 → reescreve gancho.

## 5. Direitos autorais (decisão necessária)
Repostar vídeo viral de terceiros sem permissão é o maior risco do projeto
(strike, demonetização, "conteúdo reutilizado"). Mitigação: pedir autorização/crédito
visível, só usar criadores que permitem, adicionar transformação real (tradução,
comentário, edição), e **gameplay próprio/GTA VI oficial (trailers liberados)** como fonte segura.

## 6. Entrega
Fase A: scaffold + skill /viralizei + template + 1 vídeo de teste ponta a ponta.
Fase B: lote de N vídeos em um único comando, cada um com título+descrição no próprio arquivo.
Fase C: agendamento/postagem automática.
