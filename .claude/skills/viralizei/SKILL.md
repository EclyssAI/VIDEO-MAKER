---
name: viralizei
description: Aplica métodos de viralização (gancho, estrutura, legenda, título, descrição, hashtags, loop, horário) em todo clip do canal ClipeiAki (GTA). Use ao gerar work/<id>/edit.json antes do render.
---

# /viralizei — ClipeiAki

Entrada: `work/<id>/segments.json` (transcrição com timestamps). Saída: `work/<id>/edit.json`:
```json
{"id":"..","title":"..","hook":"..","description":"..","hashtags":["#.."],
 "start":0.0,"end":18.0,"captions":[{"start":0.0,"end":0.8,"text":"PT-BR curto"}]}
```

## Regras (aplicar SEMPRE)
1. **Corte**: começar 1 beat ANTES do momento-chave; terminar logo após o payoff. Meme 10–20 s, curiosidade 25–45 s, máx 59 s.
2. **Hook** (≤7 palavras, PT-BR, aparece 0–3 s): promessa/choque/pergunta. Ex.: "NINGUÉM ESPERAVA ISSO NO GTA", "ESSE DETALHE DO GTA 6 É LOUCO".
3. **Estrutura**: gatilho → contexto curto → escalada → reação → payoff → fim seco.
4. **Legendas**: traduzir para PT-BR natural (gíria gamer, sem tradução literal), 2–3 palavras por bloco, casando com o timestamp original. Tudo em lote numa única resposta (economia de tokens).
5. **Título** ≤60 chars, gatilho de curiosidade + keyword (GTA 6 / GTA RP). Gerar 3 variações internamente, entregar a melhor.
6. **Descrição**: 1ª linha = gancho; 1 linha de contexto; CTA "Segue o @ClipeiAki"; hashtags (3–5 específicas + base do canal).
7. **Loop**: se possível, final que emenda com o início.
8. **Curiosidade vs meme**: curiosidade = fato + "você sabia?"; meme = reação/humor, mínimo de texto.
9. **Postar**: 1–3/dia, qualidade > volume, pergunta nos comentários ("qual seu GTA favorito?"), responder comentários na 1ª hora.

## Fluxo
`python pipeline/run.py prepare` → gerar edit.json de TODOS os vídeos num único passo → `python pipeline/run.py render` (roda `viralizei_check.py`; score <70 → reescrever hook/título e rodar de novo).

## Modo LIVE (cortes da madrugada)
Ao ver `BATCH_READY <dir>`: ler SÓ `<dir>/for_claude.txt` (texto compacto), escrever `<dir>/copy.json` de TODOS os cortes numa única escrita, rodar `python live/render_live.py <dir>` e entregar a lista (nº, título, thumb). Nunca abrir vídeo/transcrição inteira.
```json
{"<id>": {"title": "≤60 chars, reação + GTA", "description": "1ª linha gancho", "hashtags": ["#gtarp"],
          "captions": [{"s": 9.5, "e": 11.2, "t": "PT-BR curto", "hl": true}]}}
```
- `captions` em segundos relativos ao início do corte (o pico = campo `peak`); `hl: true` = palavra-chave em rosa (máx 1–2 por corte).
- Títulos de reação: "ELE NÃO ESPERAVA ISSO 😱", "O SUSTO QUE ELE LEVOU KKKK", "A REAÇÃO MAIS ABSURDA DO GTA RP".
- B-roll: apenas o punch-in de zoom no pico (automático). SFX: whoosh no início (-15 dB) + impacto no pico (-6 dB); nada além disso (regras da skill `sound`).
- Aprovação: o usuário responde os números → `python esteira.py approve <lote> 1 3`.

## Rotação anti-repetição (adaptado da skill viral-tiktok-hooks)
Nunca repetir o mesmo ângulo em cortes seguidos do mesmo lote. Escolher 1 ângulo por corte:
| Ângulo | Forma do título (PT-BR) |
|---|---|
| Curiosity Gap | "Ninguém fala desse detalhe do GTA 6" / "O que acontece se você…" |
| Choque/Reação | "Ele NÃO esperava isso 😱" / "O susto que ele levou KKKK" |
| Número específico | "3 segundos que mudaram a live inteira" |
| Desafio/Prova | "Disseram que era impossível no GTA… olha isso" |
| Identidade | "Todo jogador de GTA RP já passou por isso" |
| Loop aberto | "Espera o final…" (só se o payoff estiver nos últimos 2 s) |
Regras: loop aberto nos 2 primeiros segundos; especificidade > adjetivo; 1 emoji no máximo; CTA de comentário na descrição.

## Regras do dono do canal (v0.4 — valem SEMPRE, acima das anteriores)
1. **Legenda = só tradução da fala.** Proibido comentário/narração nossa ("VOOU PELO PARA-BRISA", "KKKK"). Sem fala = sem legenda. Palavrão traduzido e censurado (P*RRA).
2. **Título no molde gringo + gatilho de comentário.** Tela (`screen_title`, ≤35 chars): molde gringo traduzido. Post (`title`, ≤60): molde + pergunta que divide opinião.
   Moldes gringos (canais de clips US): "X Reacts to Y For The First Time 😭" → "X vendo Y pela 1ª vez 😭" · "X Can't Stop Y 💀" → "X não consegue parar de Y 💀" · "Bro Had ONE Job…" → "Ele só tinha UMA missão…" · "X Was NOT Ready For This" → "X NÃO tava pronto pra isso" · "Chat Made X Do Y" → "O chat fez X Y" · "POV: …".
   Perguntas de engajamento: "Você vai jogar dia 19?", "Quem dirige pior: ele ou você?", "Isso foi bug ou skill?".
3. **Monetização:** priorizar vídeos de **61–90 s** (TikTok Creator Rewards exige > 1 min). Se um clip é curto, montar **compilação** com arco narrativo (expectativa → clímax → payoff) via `_compilation` no copy.json:
   `{"_compilation": {"order": ["a","b"], "screen_title": "...", "title": "...", "description": "...", "hashtags": [...]}, "a": {"captions": [...]}}`
4. Streamer fora do centro em layout sem webcam: usar `focus` (0–1, fração da largura) no pending.json.
5. Mascote encosta na barra inferior (template/assets/mascot.png já ajustado).

## Padrão dos clipadores grandes (v0.5 — aplicar em TODO vídeo)
1. **Cold open:** os primeiros 1,5–2,5 s são o clímax (rosto + grito/frase mais forte), depois a história do começo. Nunca abrir com fala calma. O frame 0 precisa ter rosto ou ação.
2. **Cortes secos:** remover silêncio > 0,7 s e trechos sem fala nem ação (navegar em menu, tela parada). Cada trecho vira uma entrada no pending.json.
3. **Ritmo visual:** alternar `zoom` 1.0 / 1.10–1.18 entre trechos consecutivos do mesmo plano (simula troca de câmera). Trecho > 10 s sem corte = dividir.
4. **Legenda karaokê:** automática (palavra falada em amarelo e maior; `hl` muda a cor-base do bloco para rosa).
5. **Layout por trecho:** webcam pequena sobre conteúdo do jogo → `webcam` (layout dividido); webcam ocupando a tela → sem webcam + `focus` no rosto.
6. **Checagem antes de entregar:** frame 0 com rosto/ação; nenhum silêncio > 1 s (`silencedetect`); duração 61–90 s; -14 LUFS; 30 fps.
