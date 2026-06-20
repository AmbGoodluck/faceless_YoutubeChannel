# Lights Out Tales — Pipeline Status Report

_Channel:_ **Lights Out Tales** (@thelightsouttales) · _Style:_ photoreal cinematic · _Voice:_ `en-US-GuyNeural` (deep, calm, slowed) · _Cost:_ $0/month

---

## The full flow (end to end)

```
1. content_queue.csv        idea (10 episodes pre-loaded)
2. generate_script.py        Gemini writes the script        ──► Slack: "script ready" + approve cmd   [APPROVE 1]
3. generate_voice.py         Edge TTS narration (Guy voice)
4. generate_visuals.py       Pollinations photoreal images
5. render_video.py           FFmpeg: images + voice + captions = final.mp4  ──► Slack: "video ready"   [APPROVE 2]
6. upload_youtube.py         long-form upload to YouTube
7. clip_for_tiktok.py        split into 3 vertical clips (PART 1/2/3 + CTA)  ──► Slack: "published"
8. Metricool                 you queue the 3 clips → TikTok + YouTube Shorts @ 08:00 / 13:00 / 19:00
```

Two human approvals (script, then video) — nothing posts without you seeing it.

---

## Status: what's DONE ✅

| Piece | State |
|---|---|
| Story-world, brand, name, logo/banner/thumbnail | ✅ done |
| Repo + full $0 pipeline code | ✅ on GitHub `main`, all compiles |
| Script generation (Gemini, free) | ✅ working — you ran it |
| Voice (Edge TTS, Guy) | ✅ coded, installed |
| Visuals (Pollinations, photoreal) | ✅ coded; style locked |
| Video assembly + captions (FFmpeg) | ✅ coded; ffmpeg installed |
| 3-clip TikTok/Shorts splitter | ✅ coded |
| Slack notifications (script + video link) | ✅ just added |
| Daily scheduler (GitHub Actions) | ✅ written (needs enabling) |
| Python deps + ffmpeg on your Mac | ✅ installed |
| TikTok + Metricool connected | ✅ you did this |

## Status: what's STILL NEEDED ⚠️ (your action)

| # | Action | Why |
|---|---|---|
| 1 | **Rotate the GitHub token** (new one with `workflow` scope) | old one was pasted in chat; scope lets Actions file live in `.github/workflows/` |
| 2 | **Rotate the Gemini key** | it was pasted in chat too |
| 3 | **Connect YouTube in Metricool** | so the 3 clips post to YouTube Shorts as well as TikTok |
| 4 | **YouTube API: `client_secret.json`** | needed for the long-form auto-upload (README step 5) |
| 5 | **Slack incoming webhook** → put in `.env` as `SLACK_WEBHOOK_URL` | turns on the daily script + video-link messages |
| 6 | **Enable the GitHub Action** + add repo secrets `GEMINI_API_KEY`, `SLACK_WEBHOOK_URL` | daily auto script generation |
| 7 | **First full test run** of `--render 1` then `--publish 1` | confirm voice + visuals + render look right |

---

## How scheduling works (two separate schedules)

**A. Script generation — automatic, daily.**
GitHub Actions (`setup/daily.yml.txt`) runs every morning, generates the next queued
script, commits it, and pings Slack. Enable it: create `.github/workflows/daily.yml`
with that file's contents, then add the two repo secrets above. Change the time via
the `cron` line (currently 13:00 UTC).

**B. Posting — scheduled in Metricool.**
After you approve a video, you drop the 3 clips into Metricool and set the daily
times. In Metricool: connect TikTok + YouTube (+ Instagram if you want) → use the
**Planner/Auto-lists** to set recurring slots at **08:00 / 13:00 / 19:00** → upload
the 3 clips into those slots. Metricool posts to TikTok **and** YouTube Shorts from
one upload. The long-form YouTube video uploads automatically at the `--publish` step.

> The times live in `config.py → TIKTOK_DAYPARTS` (the clip filenames/plan use them);
> the actual scheduled posting is set in Metricool.

---

## Your viewing & approval (Slack)

Once `SLACK_WEBHOOK_URL` is set, Slack becomes your control panel:
- **Daily:** the new script arrives in Slack to read. Approve by running the render command it shows.
- **After render:** Slack posts that the video is ready (watch `final.mp4` locally — your safe pre-post check).
- **After publish:** Slack confirms the YouTube link + that the 3 clips are ready for Metricool.

**On true one-click Slack buttons:** approving by *clicking a button in Slack* (instead
of running a command) needs a tiny always-on endpoint (a Slack app). It's buildable and
still free (e.g. a Cloudflare Worker), but it's an extra setup. The webhook version above
works right now with zero hosting. Say the word and I'll build the button version next.

---

## Gaps / nice-to-haves (optional, not blocking)

- **Background ambience:** no music/SFX yet. A faint free ambient drone under the
  narration boosts retention — easy to add to `render_video.py`.
- **Captions** are evenly timed, not word-synced. Fine for now; can upgrade to Whisper
  word-timing later for perfect sync.
- **Per-episode thumbnails:** you have a template; auto-generating one per long-form video can be added.
- **Fully-automatic posting everywhere:** free Metricool = you drop clips into the queue.
  Hands-off auto-posting needs Metricool's paid API (or direct TikTok API). Free path is
  ~2 min of dragging clips into Metricool per video.

---

## The daily runbook (once everything's on)
```
# (automatic) morning: GitHub Action generates script -> Slack
python src/run_pipeline.py --render 1     # approve script -> builds video -> Slack
open outputs/1-*/final.mp4                 # safe watch
python src/run_pipeline.py --publish 1     # approve -> YouTube long-form + 3 clips
# drop the 3 clips into Metricool (TikTok + YouTube Shorts) -> done
```
Weekly: add 7 new rows to `content_queue.csv`.
