# Postagem automática grátis (APIs oficiais) — credenciais em config/secrets/ (nunca no git)
| Plataforma | Arquivo | Como obter (grátis) |
|---|---|---|
| YouTube Shorts | `youtube_token.json` | Google Cloud → ativar YouTube Data API v3 → OAuth "Desktop" → rodar fluxo uma vez (`google-auth-oauthlib`, escopo `youtube.upload`) e salvar `creds.to_json()`. Cota grátis ≈ 6 uploads/dia. |
| Instagram Reels | `instagram.json` `{"ig_user_id","access_token"}` | Conta Instagram Profissional ligada a uma Página do Facebook → app em developers.facebook.com → permissões `instagram_content_publish`, `pages_read_engagement` → token de longa duração (60 dias). Limite 50 posts/24h. |
| TikTok | `tiktok.json` `{"client_key","client_secret","refresh_token","expires_at":0}` | developers.tiktok.com → app com "Content Posting API" (Direct Post) + escopo `video.publish`. **Antes da auditoria do app os posts saem como privados** (`privacy: SELF_ONLY` no publish.yaml). |
Alternativa com painel visual, grátis e self-hosted: **Postiz** (github.com/gitroomhq/postiz-app, AGPL) — usa os mesmos apps acima.
