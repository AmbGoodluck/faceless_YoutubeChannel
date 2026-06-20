"""
Upload / download files to Google Drive using the headless cloud credentials.
Used to store the rendered video + clips so you can watch and download them.
"""
import os, sys, io
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import google_auth


def _svc():
    return build("drive", "v3", credentials=google_auth.creds())


def upload(path: str, folder_id: str | None = None, name: str | None = None,
           public: bool = True) -> dict:
    svc = _svc()
    meta = {"name": name or os.path.basename(path)}
    if folder_id:
        meta["parents"] = [folder_id]
    f = svc.files().create(
        body=meta,
        media_body=MediaFileUpload(path, resumable=True),
        fields="id,webViewLink",
    ).execute()
    fid = f["id"]
    if public:  # anyone-with-link can view (so the Slack watch link works)
        svc.permissions().create(
            fileId=fid, body={"role": "reader", "type": "anyone"}).execute()
    print(f"[drive] uploaded {meta['name']} -> {f.get('webViewLink')}")
    return {"id": fid, "link": f.get("webViewLink")}


def download(file_id: str, dest: str) -> str:
    svc = _svc()
    req = svc.files().get_media(fileId=file_id)
    with io.FileIO(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
    print(f"[drive] downloaded {file_id} -> {dest}")
    return dest


def ensure_folder(name: str, parent: str | None = None) -> str:
    """Find or create a Drive folder, return its id."""
    svc = _svc()
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
         "and trashed=false")
    if parent:
        q += f" and '{parent}' in parents"
    hits = svc.files().list(q=q, fields="files(id)").execute().get("files", [])
    if hits:
        return hits[0]["id"]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent:
        meta["parents"] = [parent]
    return svc.files().create(body=meta, fields="id").execute()["id"]
