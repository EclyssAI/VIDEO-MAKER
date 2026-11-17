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
