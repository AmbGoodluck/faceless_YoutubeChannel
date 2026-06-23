"""
Upload to YouTube via the Data API.

Two modes:
  - Local/interactive: if client_secret.json is present and no GOOGLE_REFRESH_TOKEN,
    opens a browser once (token cached in token.json).
  - Cloud/headless: if GOOGLE_REFRESH_TOKEN is set (GitHub Actions), uses that — no browser.

upload(out_dir)       -> uploads final.mp4 as a normal video (sets thumbnail.jpg if present)
upload_short(path,..)  -> uploads a vertical clip as a Short (#Shorts in title)
"""
import os, sys
import googleapiclient.discovery
import googleapiclient.http

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(HERE, "..", "client_secret.json")
TOKEN = os.path.join(HERE, "..", "token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Appended to every description for YouTube transparency / disclosure guidelines.
DISCLAIMER = (
    "\n\n———\n"
    "⚠️ DISCLAIMER: This is a work of FICTION for entertainment. Names, characters, places "
    "and events are products of the imagination; any resemblance to real persons (living or "
    "dead) or actual events is purely coincidental.\n"
    "This video contains AI-GENERATED visuals and SYNTHETIC (AI) voices.\n"
    "Intended for mature teen+ audiences (13+). No graphic violence or gore.\n"
    "If you or someone you know is struggling, please reach out to a trusted person or local "
    "support service."
)


def _service():
    if os.environ.get("GOOGLE_REFRESH_TOKEN"):           # cloud / headless
        from src import google_auth
        return googleapiclient.discovery.build("youtube", "v3", credentials=google_auth.creds())
    # local interactive fallback
    import google.oauth2.credentials, google.auth.transport.requests
    import google_auth_oauthlib.flow
    creds = None
    if os.path.exists(TOKEN):
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        open(TOKEN, "w").write(creds.to_json())
    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def _insert(yt, path, title, description, tags, privacy="public"):
    body = {"snippet": {"title": title[:100], "description": description,
                        "tags": tags, "categoryId": "24"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    media = googleapiclient.http.MediaFileUpload(path, chunksize=-1, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"[youtube] {int(status.progress()*100)}%")
    return resp["id"]


def upload(out_dir: str, privacy="public") -> str:
    import json
    script = json.load(open(os.path.join(out_dir, "script.json")))
    yt = _service()
    vid = _insert(yt, os.path.join(out_dir, "final.mp4"),
                  script.get("youtube_title", script["title"]),
                  script.get("youtube_description", "") + DISCLAIMER,
                  script.get("hashtags", []), privacy)
    thumb = os.path.join(out_dir, "thumbnail.jpg")
    if os.path.exists(thumb):
        try:
            yt.thumbnails().set(videoId=vid,
                media_body=googleapiclient.http.MediaFileUpload(thumb)).execute()
            print("[youtube] thumbnail set")
        except Exception as e:
            print(f"[youtube] thumbnail skipped: {e}")
    print(f"[youtube] uploaded https://youtu.be/{vid}")
    return vid


def upload_short(path: str, title: str, description: str, tags: list, privacy="public") -> str:
    yt = _service()
    vid = _insert(yt, path, (title + " #Shorts")[:100], description + "\n\n#Shorts" + DISCLAIMER, tags, privacy)
    print(f"[youtube] Short uploaded https://youtu.be/{vid}")
    return vid


if __name__ == "__main__":
    upload(sys.argv[1])
