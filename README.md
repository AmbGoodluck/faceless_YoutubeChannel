# Lights Out Tales — Automated Pipeline

A "script factory" for a faceless horror channel. It pulls the next idea from a
queue, writes a finished script in the channel's exact voice, and hands it to
**Revid.ai**, which generates the voiceover + visuals + captions and can auto-post
to TikTok and YouTube. Two quick human checkpoints keep it inside YouTube's
authenticity rules.

```
content_queue.csv ─▶ generate_script.py ─▶ [approve] ─▶ revid_client.py ─▶ [approve] ─▶ YouTube
   (ideas)            (Claude, brand voice)  script.txt    (video+voice)     final cut      (full story)
                                                                                  │
                                                                  clip_for_tiktok.py
                                                                                  │
                                              3 vertical clips ─▶ TikTok @ 08:00 / 13:00 / 19:00
                                              (PART 1 / 2 / 3, with "full story on YouTube" CTA)
```

---

## What it costs

| Service | Why | Plan needed |
|---|---|---|
| Anthropic API | Writes the scripts | Pay-as-you-go, ~cents per script |
| Revid.ai | Voiceover + visuals + captions + auto-post | **Growth plan** (required for API; ~$39/mo promo) |
| GitHub Actions | Runs it on a daily timer | Free tier |

> This path is **not** $0 — Revid's API needs the Growth plan. If you'd rather stay free, the alternative is the Edge-TTS + Pollinations + Remotion stack from the master plan (more setup, no monthly fee). You picked the automated-tool route, so this repo is built around Revid.

---

## Step-by-step setup (do these in order)

### 1. Anthropic API key (script generation)
1. Go to **https://console.anthropic.com** and sign in.
2. Add a payment method under **Billing** (scripts cost ~$0.01–0.03 each).
3. **Settings → API Keys → Create Key**. Copy it.

### 2. Revid.ai account + API key (video)
1. Sign up at **https://www.revid.ai** and subscribe to the **Growth** plan (API access requires it).
2. Open **https://www.revid.ai/account** and copy your **API key**.
3. In the Revid editor, pick a **deep, calm male narrator voice** and copy its `voiceId`.
4. Go to **https://www.typeframes.com/create → "…" → "Get API Code"** and copy the
   current request parameters. Paste any new fields into `build_payload()` in
   `src/revid_client.py` and set `voiceId` + look in `config.py → REVID_DEFAULTS`.

### 3. Connect your social accounts to Revid (auto-posting)
1. In Revid, open the **Auto-Post / Social** settings.
2. Connect **YouTube** (the Lights Out Tales channel) and **TikTok** (@thelightsouttales).
3. Set posting times. Revid will publish approved renders straight to both.
   *(TikTok's own API is hard to get directly — letting Revid post is the easy path.)*

### 4. Run it locally first
```bash
git clone <this repo>
cd faceless_YoutubeChannel
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your real keys into .env
export $(grep -v '^#' .env | xargs)   # load keys into your shell

python src/run_pipeline.py            # writes the next script, stops for your review
# read outputs/1-the-note-on-the-windshield/script.txt
python src/run_pipeline.py --submit 1 # sends the approved script to Revid
```

### 5. Put it on a schedule (GitHub Actions)
1. Push this repo to GitHub.
2. **Repo → Settings → Secrets and variables → Actions → New secret**:
   add `ANTHROPIC_API_KEY` (and `REVID_API_KEY` when you automate submission).
3. `.github/workflows/daily.yml` already runs every morning and commits the day's
   script. Adjust the `cron` time to your timezone.

---

### 6. Clip each YouTube video into 3 TikTok parts (morning / afternoon / evening)
Every full video that goes to YouTube is split into 3 vertical clips and posted to
TikTok across the day, each labelled PART 1/2/3 with a "full story on YouTube" CTA.
```bash
python src/clip_for_tiktok.py outputs/1-the-note-on-the-windshield/final.mp4
```
This writes `tiktok_part1.mp4 … part3.mp4` plus `tiktok_posting_plan.json` with the
three post times from `config.TIKTOK_DAYPARTS` (default 08:00 / 13:00 / 19:00 — edit there).

**To actually schedule the 3 posts**, pick one:
- **TikTok native scheduler** (free): upload the 3 clips on tiktok.com, set each post
  time. Schedules up to 10 days ahead. Most reliable, fully manual.
- **A social scheduler** (Metricool free tier, Buffer, or self-hosted Postiz): connect
  TikTok once, then drop the 3 clips with the planned times for hands-off posting.
- **Revid Auto-Post**: if you generate the parts as separate Revid renders, its scheduler
  can post them directly.

## Daily routine (≈20 min once it's running)
1. **Approve the script** the morning job generated (`script.txt`). Tweak a line if needed.
2. `--submit` it (or let Revid Auto-Mode pull it).
3. **Watch the finished video** Revid returns. Approve → it posts to YouTube.
4. **Clip it** with `clip_for_tiktok.py` and queue the 3 parts to TikTok for 08:00 / 13:00 / 19:00.
5. Weekly: drop 7 new rows into `content_queue.csv`.

## Growth model (built into the queue)
- Post episodes 1–10 as nightly TikTok/Shorts cliffhangers.
- Compile every 5 into an 8–12 min YouTube long-form for real RPM.
- Episodes 1 & 10 bookend a season around the "notes" motif → reason to subscribe.

## Don't skip
- **Always do the two checkpoints.** YouTube demonetizes zero-review, mass-produced AI channels.
- **Copyright:** only use Revid's licensed stock + AI assets. Unlicensed music/footage is the #1 channel killer.
- **Rotate any API key that ever gets exposed.**

## Files
| File | Role |
|---|---|
| `config.py` | Brand voice + all settings |
| `content_queue.csv` | Idea queue (10 episodes pre-loaded) |
| `src/generate_script.py` | Claude → finished script + metadata |
| `src/revid_client.py` | Revid.ai render API |
| `src/clip_for_tiktok.py` | Splits each video into 3 dayparted TikTok clips |
| `src/run_pipeline.py` | Orchestrator with the two checkpoints |
| `.github/workflows/daily.yml` | Daily scheduler |

---
### Enabling the daily scheduler
The Actions workflow ships as `setup/daily.yml.txt` (the push token lacked `workflow`
scope). To turn it on: create `.github/workflows/daily.yml` in the repo and paste that
file's contents in — either locally, or via GitHub's "Add file" web editor.
