"""
ONE-TIME local helper to mint a Google refresh token for the cloud.

Run on your Mac (needs client_secret.json from Google Cloud, Desktop OAuth client):
  python src/get_google_token.py

A browser opens; sign in with the channel's Google account and allow.
It prints GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN —
add those three as GitHub repo secrets (and to your local .env).
"""
import json, os, sys
from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import google_auth

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(HERE, "client_secret.json")


def main():
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT, google_auth.SCOPES)
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent", include_granted_scopes="false")
    info = json.load(open(CLIENT))
    c = info.get("installed", info.get("web", {}))
    if not creds.refresh_token:
        print("\n!!! Google did NOT return a refresh token (you'd already granted this app).")
        print("Fix: open https://myaccount.google.com/permissions , remove access for")
        print("'LightsOutTales' / 'lights-out-tales', then run this script again.\n")
        sys.exit(1)
    print("\n=== add these three to your .env (and later as GitHub secrets) ===")
    print("GOOGLE_CLIENT_ID=" + c["client_id"])
    print("GOOGLE_CLIENT_SECRET=" + c["client_secret"])
    print("GOOGLE_REFRESH_TOKEN=" + creds.refresh_token)


if __name__ == "__main__":
    main()
