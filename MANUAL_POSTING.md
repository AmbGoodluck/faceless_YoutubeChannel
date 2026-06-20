# Manual Posting + Daily Reminders

You post by hand, but the pipeline does everything else: writes the script, makes the
video, cuts the 3 clips, builds the thumbnail + captions, and **reminds you at
7am / 12pm / 4pm** with each clip ready to post.

## Where the videos are stored

Everything lives **locally on your Mac**, nothing on a third-party server:

- `outputs/<episode>/` — working files (voice, images, `final.mp4`).
- `to_post/<episode>/` — the **posting bundle**: the 3 clips, `thumbnail.jpg`, and
  `POST_KIT.md` (title, description, hashtags, pinned comment, per-clip captions).

To post from your **phone** (easiest for TikTok), sync just the `to_post/` folder to
your phone:
- **Google Drive** (free 15 GB): install Drive for desktop, and either keep the repo
  inside your Google Drive folder, or set Drive to back up `~/faceless_YoutubeChannel/to_post`.
- or **iCloud Drive**: move/symlink `to_post/` into iCloud Drive.

The clips then appear in your phone's Drive/Files app — open TikTok, pick the clip, paste the caption, post.

## The daily flow

1. **Render + package an episode** (do this once per episode, when you have time):
   ```
   python src/run_pipeline.py --render 1
   open outputs/1-the-note-on-the-windshield/final.mp4   # watch it
   python src/run_pipeline.py --publish 1                # makes clips + thumbnail + POST_KIT, queues them
   ```
2. **At 7am / 12pm / 4pm** your Mac reminds you and serves the next clip automatically
   (see setup below): it opens the video, copies the caption+hashtags to your clipboard,
   and pings Slack. You just switch to TikTok/YouTube, paste, attach the clip, post.

## Set up the 7am / 12pm / 4pm reminders (one-time)

These use `cron` on your Mac. Your Mac must be awake at those times.

1. Make the runner executable:
   ```
   chmod +x ~/faceless_YoutubeChannel/remind.sh
   ```
2. Open your crontab:
   ```
   crontab -e
   ```
   (press `i` to edit, paste the three lines, then `Esc`, then type `:wq` and Enter)
   ```
   0 7  * * * /Users/osmanjalloh/faceless_YoutubeChannel/remind.sh
   0 12 * * * /Users/osmanjalloh/faceless_YoutubeChannel/remind.sh
   0 16 * * * /Users/osmanjalloh/faceless_YoutubeChannel/remind.sh
   ```
3. First time, macOS may ask to grant `cron`/Terminal permission to show notifications
   and control your Mac — allow it.

Test it any time without waiting for the clock:
```
python src/serve_next_clip.py
```
It will open the next queued clip and copy its caption.

## What each post gets (built for reach)

`POST_KIT.md` per episode gives you:
- **YouTube:** a curiosity-gap title, keyword-rich description, generated `thumbnail.jpg`, and a pinned-comment question to drive replies.
- **Each clip caption:** the hook line + Part x/3 + a mix of broad and niche hashtags.

If you set up the YouTube API (`client_secret.json`), `--publish` also auto-uploads the
full video to YouTube **with the thumbnail set** — so only TikTok stays manual.
