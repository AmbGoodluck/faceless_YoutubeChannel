# Lights Out Tales — Automated Pipeline ($0 stack)

A free, faceless horror-channel factory. It pulls the next idea from a queue,
writes a script in the channel's voice, makes the voiceover + visuals, assembles a
captioned vertical video, uploads it to YouTube, and clips it into 3 TikTok parts
for morning / afternoon / evening. Two quick human checkpoints keep it inside
YouTube's authenticity rules. **No paid subscriptions.**

```
content_queue.csv ─▶ generate_script ─▶ [approve] ─▶ voice + visuals + render ─▶ [approve] ─▶ YouTube
   (ideas)            (Gemini, free)       script.txt    (EdgeTTS+Pollinations+FFmpeg)  final.mp4   (full)
                                                                                          │
                                                                                clip_for_tiktok
                                                                                          │
                                                3 vertical clips ─▶ TikTok @ 08:00 / 13:00 / 19:00
```

## What it costs: **$0/month**

| Stage | Tool | Cost |
|---|---|---|
| Script | Google Gemini API (free tier, no card) | $0 |
| Voiceover | Microsoft Edge TTS (`edge-tts`) | $0 |
| Visuals | Pollinations.ai (no key) | $0 |
| Assembly + clipping | FFmpeg | $0 |
| YouTube upload | YouTube Data API v3 | $0 (free quota) |
| Scheduler | GitHub Actions free tier | $0 |
| TikTok posting | TikTok native scheduler / Metricool free | $0 |

---

## Step-by-step setup (in order)

### 1. Install prerequisites
```bash
git clone <this repo> && cd faceless_YoutubeChannel
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# FFmpeg (system, not pip):  macOS: brew install ffmpeg   |   Ubuntu: sudo apt install ffmpeg
```

### 2. Gemini API key (script generation — FREE)
1. Go to **https://aistudio.google.com/apikey** (sign in with Google).
2. **Create API key** — no credit card needed.
3. `cp .env.example .env` and paste it as `GEMINI_API_KEY=...`

### 3. Generate your first script
```bash
export $(grep -v '^#' .env | xargs)
python src/run_pipeline.py --script
# read outputs/1-the-note-on-the-windshield/script.txt  ← CHECKPOINT 1 (approve/edit)
```

### 4. Make the video (voice + images + render — FREE)
```bash
python src/run_pipeline.py --render 1
# watch outputs/1-the-note-on-the-windshield/final.mp4  ← CHECKPOINT 2 (approve)
```
Edge TTS makes the narration, Pollinations makes one image per scene, FFmpeg adds a
slow zoom + burned captions and syncs it all to the audio length.

### 5. YouTube upload (FREE, one-time OAuth)
1. **https://console.cloud.google.com** → create a project.
2. **APIs & Services → Library →** enable **YouTube Data API v3**.
3. **Credentials → Create credentials → OAuth client ID → Desktop app.** Download the
   JSON, rename to **`client_secret.json`**, put it in the repo root.
4. First publish opens a browser to authorize; the token caches in `token.json`.
```bash
python src/run_pipeline.py --publish 1   # uploads to YouTube + makes the 3 TikTok clips
```
(If you skip `client_secret.json`, it still makes the clips — you just upload the
YouTube file by hand.)

### 6. TikTok: schedule the 3 clips (FREE)
`--publish` writes `tiktok_part1..3.mp4` + `tiktok_posting_plan.json` (times from
`config.TIKTOK_DAYPARTS`, default 08:00 / 13:00 / 19:00, each labelled PART 1/2/3
with a "full story on YouTube" CTA). To post them:
- **TikTok native scheduler** (free): upload the 3 clips on tiktok.com, set each time. Up to 10 days ahead.
- **Metricool free tier / Buffer**: connect TikTok once, drop the 3 clips with the planned times for hands-off posting.

### 7. Put script-gen on a daily timer (FREE)
1. Push to GitHub. Add repo secret **`GEMINI_API_KEY`** (Settings → Secrets → Actions).
2. Enable the workflow in `setup/daily.yml.txt` — create `.github/workflows/daily.yml`
   and paste its contents. It generates the next script each morning and commits it.

---

## Daily routine (≈15–20 min)
1. Approve the morning's `script.txt` (edit a line if needed).
2. `--render` it, watch `final.mp4`.
3. `--publish` it → YouTube + 3 TikTok clips.
4. Queue the 3 clips to TikTok for 08:00 / 13:00 / 19:00.
5. Weekly: add 7 new rows to `content_queue.csv`.

## Free-tier limits to know
- **Gemini:** 1,500 requests/day free — plenty (you need ~1/day). Prompts may be used for training on the free tier.
- **Pollinations / Edge TTS:** free and keyless; if a request times out the code retries.
- **YouTube API:** ~6 uploads/day on default quota — fine for daily posting.

## Don't skip
- **Always do the two checkpoints.** YouTube demonetizes zero-review, mass-produced AI channels.
- **Copyright:** Pollinations images are AI-generated (safe); never add unlicensed music.
- **Rotate any API key/token that ever gets exposed.**

## Files
| File | Role |
|---|---|
| `config.py` | Brand voice + all settings |
| `content_queue.csv` | Idea queue (10 episodes pre-loaded) |
| `src/generate_script.py` | Gemini → script + metadata |
| `src/generate_voice.py` | Edge TTS → voice.mp3 |
| `src/generate_visuals.py` | Pollinations → scene images |
| `src/render_video.py` | FFmpeg → captioned final.mp4 |
| `src/upload_youtube.py` | YouTube Data API upload |
| `src/clip_for_tiktok.py` | Splits each video into 3 dayparted TikTok clips |
| `src/run_pipeline.py` | Orchestrator with the two checkpoints |
| `setup/daily.yml.txt` | GitHub Actions scheduler (move into `.github/workflows/`) |

---
### Enabling the daily scheduler
The Actions workflow ships as `setup/daily.yml.txt` (the push token lacked `workflow`
scope). To turn it on, create `.github/workflows/daily.yml` and paste that file's
contents in — locally, or via GitHub's "Add file" web editor.
