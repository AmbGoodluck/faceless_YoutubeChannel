"""
Headless Google credentials for the cloud (Drive + YouTube), built from a stored
refresh token in environment variables. No browser needed at run time.

Set these (locally in .env, and as GitHub Actions secrets):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
Mint the refresh token once with src/get_google_token.py
"""
import os
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",     # upload to Drive
    "https://www.googleapis.com/auth/youtube.upload",  # post videos
]


def creds() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
