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
