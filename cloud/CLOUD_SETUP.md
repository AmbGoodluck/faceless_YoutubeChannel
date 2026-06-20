# Cloud Setup — laptop-off, Slack-approved pipeline

Goal: your laptop can be closed. Each morning GitHub's cloud writes a script and Slacks
it with an **Approve** button. You tap it → it renders the video, stores it in your Google
Drive, and Slacks the watch link with another **Approve**. You tap that → it posts to
YouTube (video + Short), uploads the 3 TikTok clips to Drive, and Slacks each caption.
You download a clip, post to TikTok, paste the caption. That's the only manual part.

```
GitHub Actions (cloud) ──Slack msg+button──▶ you tap ──▶ Cloudflare Worker ──▶ triggers next stage
   script ──▶ [approve] ──▶ render ──▶ Drive + [approve] ──▶ publish ──▶ YouTube + Drive + Slack captions
```

Do these in order. Each is one-time.

## 1. Google OAuth (Drive + YouTube) — the prerequisite
1. https://console.cloud.google.com → your project.
2. **APIs & Services → Library** → enable **YouTube Data API v3** AND **Google Drive API**.
3. **OAuth consent screen** → External → add your Gmail as a **Test user** (keep it in Testing).
4. **Credentials → Create credentials → OAuth client ID → Desktop app** → Download JSON →
   save as `client_secret.json` in the repo root.
5. On your Mac, once:
   ```
   source .venv/bin/activate
   pip install -r requirements.txt
   python src/get_google_token.py
   ```
   A browser opens → allow. It prints `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   `GOOGLE_REFRESH_TOKEN`. Keep these for step 5.

## 2. Google Drive folder
1. In Google Drive, create a folder named **Lights Out Tales**.
2. Open it; the URL ends in `/folders/XXXXX` — copy `XXXXX`. That's `GDRIVE_FOLDER_ID`.

## 3. Slack app — turn on buttons
1. Your existing Slack app (the one with the webhook) → **Interactivity & Shortcuts → toggle On**.
2. **Request URL:** paste your Worker URL from step 4 (come back after deploying it).
3. **Basic Information → App Credentials → Signing Secret** → copy it for step 4.

## 4. Cloudflare Worker (the Approve-button catcher)
1. Free account at cloudflare.com. Install the CLI: `npm install -g wrangler`.
2. ```
   cd cloud/worker
   wrangler login
   ```
3. Confirm `GH_OWNER`/`GH_REPO` in `wrangler.toml` are right.
4. Create a GitHub **fine-grained PAT** (github.com → Settings → Developer settings →
   Fine-grained tokens) scoped to this repo with **Actions: Read and write**. Then:
   ```
   wrangler secret put GH_TOKEN              # paste the PAT
   wrangler secret put SLACK_SIGNING_SECRET  # paste from step 3
   wrangler deploy
   ```
5. Copy the deployed Worker URL → paste it into Slack (step 3, Request URL) → Save.

## 5. GitHub repo secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**, add:
`GEMINI_API_KEY`, `SLACK_WEBHOOK_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`GOOGLE_REFRESH_TOKEN`, `GDRIVE_FOLDER_ID`.

## 6. Turn the workflow on
Create `.github/workflows/pipeline.yml` with the contents of
`cloud/workflows/pipeline.yml.txt` (paste via GitHub's "Add file" web editor, or push
with a `workflow`-scoped token). Adjust the `cron` time (it's UTC) to fire before your 7am.

## 7. Test it
1. Repo → **Actions → Lights Out Tales pipeline → Run workflow** → stage `script`.
2. Slack should show the script + **Approve → render**. Tap it.
3. You get the Drive watch link + **Approve → publish**. Watch, tap.
4. A few minutes later: YouTube has the video + Short, and Slack lists the 3 clips with
   captions + Drive download links.

Once it works, the daily cron runs step 1 every morning automatically — laptop off.

### What stays manual
Posting the 3 clips to **TikTok** (download from Drive, paste the caption from Slack). That's
the one thing no free path can automate.

### Costs
All free tiers: GitHub Actions (2,000 min/mo), Cloudflare Workers (100k req/day),
Gemini, Edge TTS, Pollinations, Drive (15 GB), YouTube API.
