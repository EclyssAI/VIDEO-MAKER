"""Instagram Reels pela Graph API com upload resumível (arquivo local, sem precisar hospedar o vídeo)."""
import json, time, requests
G = "https://graph.facebook.com/v21.0"
def post(video, title, desc, sec):
    s = json.loads((sec/"instagram.json").read_text()); uid, tok = s["ig_user_id"], s["access_token"]
    c = requests.post(f"{G}/{uid}/media", data={"media_type": "REELS", "upload_type": "resumable", "caption": f"{title}\n\n{desc}"[:2200],
                      "share_to_feed": "true", "access_token": tok}, timeout=60).json()
    if "id" not in c: raise RuntimeError(c)
    data = video.read_bytes()
    requests.post(c["uri"], data=data, headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(data))}, timeout=600).raise_for_status()
    for _ in range(60):
        st = requests.get(f"{G}/{c['id']}", params={"fields": "status_code", "access_token": tok}, timeout=30).json().get("status_code")
        if st == "FINISHED": break
        if st == "ERROR": raise RuntimeError("instagram: processamento falhou")
        time.sleep(10)
    r = requests.post(f"{G}/{uid}/media_publish", data={"creation_id": c["id"], "access_token": tok}, timeout=60).json()
    if "id" not in r: raise RuntimeError(r)
    return f"instagram:{r['id']}"
