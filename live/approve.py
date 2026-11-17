"""Aprovação: python live/approve.py <batch> 1 3 5   (números dos cortes) -> marca aprovado e posta.
Postagem: YouTube Shorts via API (config/secrets/youtube_token.json). Sem token: fica 'pronto_para_postar'
(suba pelo agendador do ViceScale)."""
import sys, json, pathlib
R = pathlib.Path(__file__).resolve().parent.parent; TOK = R/"config/secrets/youtube_token.json"

def post_youtube(d, m):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=Credentials.from_authorized_user_file(str(TOK)))
    body = {"snippet": {"title": m["title"][:100], "description": m["description"], "categoryId": "20"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    r = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(d/"video.mp4"), resumable=True)).execute()
    return f"https://youtube.com/shorts/{r['id']}"

b = R/"output/live"/sys.argv[1]; nums = {int(x) for x in sys.argv[2:]}
for d in sorted(b.iterdir()):
    n = int(d.name[:2]); m = json.loads((d/"meta.json").read_text())
    if n not in nums: m["status"] = "reprovado"
    elif TOK.exists(): m["status"], m["url"] = "postado", post_youtube(d, m)
    else: m["status"] = "pronto_para_postar"
    (d/"meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1)); print(n, m["status"], m.get("url", ""))
