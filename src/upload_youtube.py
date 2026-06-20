"""
Stage 6 — Upload the finished video to YouTube (FREE via YouTube Data API v3).

One-time setup (see README step 5):
  - Google Cloud project -> enable "YouTube Data API v3"
  - OAuth client (Desktop) -> download client_secret.json into this folder
  - First run opens a browser to authorize; the token is cached in token.json

Uploads as a Short if it's vertical & <=3 min (YouTube auto-detects).
"""
import os, sys, json
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.http
import google.auth.transport.requests
import google.oauth2.credentials

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(HERE, "..", "client_secret.json")
TOKEN = os.path.join(HERE, "..", "token.json")


def _service():
    creds = None
    if os.path.exists(TOKEN):
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())
    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def upload(out_dir: str, privacy="public") -> str:
    script = json.load(open(os.path.join(out_dir, "script.json")))
    video = os.path.join(out_dir, "final.mp4")
    yt = _service()
    body = {
        "snippet": {
            "title": script.get("youtube_title", script["title"]),
            "description": script.get("youtube_description", ""),
            "tags": script.get("hashtags", []),
            "categoryId": "24",  # Entertainment
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = googleapiclient.http.MediaFileUpload(video, chunksize=-1, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"[youtube] {int(status.progress()*100)}%")
    vid = resp["id"]
    # set the custom thumbnail if we generated one
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


if __name__ == "__main__":
    upload(sys.argv[1])
