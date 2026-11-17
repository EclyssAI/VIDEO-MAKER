from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
def post(video, title, desc, sec):
    yt = build("youtube", "v3", credentials=Credentials.from_authorized_user_file(str(sec/"youtube_token.json")))
    r = yt.videos().insert(part="snippet,status", media_body=MediaFileUpload(str(video), resumable=True),
        body={"snippet": {"title": title[:100], "description": desc, "categoryId": "20"},
              "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}).execute()
    return f"https://youtube.com/shorts/{r['id']}"
