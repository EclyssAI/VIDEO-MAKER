"""TikTok Content Posting API (Direct Post, upload de arquivo). Renova o access_token (24h) com o refresh_token."""
import json, time, requests
T = "https://open.tiktokapis.com/v2"
def _token(sec):
    p = sec/"tiktok.json"; s = json.loads(p.read_text())
    if time.time() > s.get("expires_at", 0) - 300:
        r = requests.post(f"{T}/oauth/token/", data={"client_key": s["client_key"], "client_secret": s["client_secret"],
                          "grant_type": "refresh_token", "refresh_token": s["refresh_token"]}, timeout=30).json()
        if "access_token" not in r: raise RuntimeError(r)
        s.update(access_token=r["access_token"], refresh_token=r["refresh_token"], expires_at=time.time()+r["expires_in"]); p.write_text(json.dumps(s))
    return s["access_token"]
def post(video, title, desc, sec, privacy="PUBLIC_TO_EVERYONE"):
    tok = _token(sec); n = video.stat().st_size; h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}
    r = requests.post(f"{T}/post/publish/video/init/", headers=h, timeout=60, json={
        "post_info": {"title": f"{title} {desc.split(chr(10))[-1]}"[:2200], "privacy_level": privacy, "disable_comment": False},
        "source_info": {"source": "FILE_UPLOAD", "video_size": n, "chunk_size": n, "total_chunk_count": 1}}).json()
    if r.get("error", {}).get("code") != "ok": raise RuntimeError(r)
    d = r["data"]
    requests.put(d["upload_url"], data=video.read_bytes(), timeout=600,
                 headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{n-1}/{n}"}).raise_for_status()
    for _ in range(60):
        st = requests.post(f"{T}/post/publish/status/fetch/", headers=h, json={"publish_id": d["publish_id"]}, timeout=30).json()["data"]["status"]
        if st == "PUBLISH_COMPLETE": return f"tiktok:{d['publish_id']}"
        if st == "FAILED": raise RuntimeError("tiktok: publicação falhou")
        time.sleep(10)
    return f"tiktok:{d['publish_id']}(processando)"
