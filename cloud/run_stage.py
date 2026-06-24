"""
Cloud orchestrator — runs ONE stage of the pipeline inside GitHub Actions.

Stages (each is a separate Actions run, triggered by your Slack approval):
  script   : pick next queued episode, write script, Slack it with an Approve button
  render   : build video, upload it to Drive, Slack the watch link + Approve button
  publish  : post to YouTube (video + Short), upload 3 clips to Drive, Slack captions

State between runs is kept in outputs/<slug>/state.json (committed by the workflow)
and the rendered media lives in your Google Drive.

Usage:
  python cloud/run_stage.py script
  python cloud/run_stage.py render  --episode <slug>
  python cloud/run_stage.py publish --episode <slug>
"""
import os, sys, csv, json, glob, argparse, tempfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import (generate_script, generate_voice, generate_visuals, render_video,
                 clip_for_tiktok, make_thumbnail, upload_drive, upload_youtube, slack_blocks)

QUEUE = config.QUEUE_FILE
ROOT_FOLDER = os.environ.get("GDRIVE_FOLDER_ID") or None


def _rows():
    with open(QUEUE, newline="") as f:
        return list(csv.DictReader(f))


def _save(rows):
    with open(QUEUE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)


def _set_status(rows, rid, status):
    for r in rows:
        if r["id"] == rid:
            r["status"] = status
    _save(rows)


def _dir(slug):
    return os.path.join(config.OUTPUT_DIR, slug)


def _state(slug):
    p = os.path.join(_dir(slug), "state.json")
    return json.load(open(p)) if os.path.exists(p) else {"slug": slug}


def _save_state(slug, st):
    json.dump(st, open(os.path.join(_dir(slug), "state.json"), "w"), indent=2)


def _captions(script):
    tags = " ".join("#" + t.lstrip("#") for t in script.get("hashtags", []))
    base = script.get("tiktok_caption", script.get("title", ""))
    return tags, base


# ---------------------------------------------------------------- stages
def stage_script():
    from src import story
    spec = story.next_episode_spec()
    data = generate_script.generate_episode(spec)
    slug = data["slug"]
    story.save_recap(data.get("recap_for_next", ""))
    _save_state(slug, {"slug": slug, "id": data["id"]})
    slack_blocks.script_for_approval(slug, data)
    print(f"::notice::script ready {slug}")


def stage_render(slug):
    out = _dir(slug)
    script = json.load(open(os.path.join(out, "script.json")))
    generate_voice.make_voice(out, script.get("voice_map", {}))   # multi-voice screenplay
    generate_visuals.make_visuals(script["scene_prompts"], out)
    if config.VIDEO_MODE == "ai":
        from src import generate_ai_video
        generate_ai_video.animate(script["scene_prompts"], out)
    elif config.VIDEO_MODE == "runpod":
        from src import generate_runpod_video
        generate_runpod_video.animate(script["scene_prompts"], out)
    render_video.render(out)
    clip_for_tiktok.clip_video(os.path.join(out, "final.mp4"))
    make_thumbnail.make(out)

    folder = upload_drive.ensure_folder(slug, ROOT_FOLDER)
    st = _state(slug); st["drive_folder"] = folder
    st["final"] = upload_drive.upload(os.path.join(out, "final.mp4"), folder, f"{slug}-FULL.mp4")
    st["thumb"] = upload_drive.upload(os.path.join(out, "thumbnail.jpg"), folder, "thumbnail.jpg")
    tags, base = _captions(script)
    st["clips"] = []
    for clip in sorted(glob.glob(os.path.join(out, "tiktok_part*.mp4"))):
        part = int(os.path.basename(clip).split("part")[1].split(".")[0])
        up = upload_drive.upload(clip, folder, os.path.basename(clip))
        up.update({"part": part, "caption": f"{base} (Part {part}/3)\n\n{tags}"})
        st["clips"].append(up)
    st["clips"].sort(key=lambda c: c["part"])
    _save_state(slug, st)
    rows = _rows(); _set_status(rows, st.get("id", slug.split("-")[0]), "rendered")
    slack_blocks.video_for_approval(slug, script.get("youtube_title", slug), st["final"]["link"])
    print(f"::notice::rendered {slug}")


def stage_publish(slug):
    out = _dir(slug)
    script = json.load(open(os.path.join(out, "script.json")))
    st = _state(slug)
    tmp = tempfile.mkdtemp()
    # download the full video back from Drive and post it to YouTube
    full = upload_drive.download(st["final"]["id"], os.path.join(tmp, "final.mp4"))
    # need script.json + thumbnail next to it for upload()
    json.dump(script, open(os.path.join(tmp, "script.json"), "w"))
    if os.path.exists(os.path.join(out, "thumbnail.jpg")):
        import shutil; shutil.copy(os.path.join(out, "thumbnail.jpg"), tmp)
    yt_video = upload_youtube.upload(tmp)
    # first clip as a Short
    yt_short = None
    if st.get("clips"):
        c1 = upload_drive.download(st["clips"][0]["id"], os.path.join(tmp, "part1.mp4"))
        yt_short = upload_youtube.upload_short(
            c1, script.get("youtube_title", slug),
            script.get("youtube_description", ""), script.get("hashtags", []))
    st["youtube"] = {"video": yt_video, "short": yt_short}
    _save_state(slug, st)
    rows = _rows(); _set_status(rows, st.get("id", slug.split("-")[0]), "posted")
    slack_blocks.published(script.get("youtube_title", slug),
                           f"https://youtu.be/{yt_video}", st["clips"])
    print(f"::notice::published {slug}")


RENDER_TRIES = 3
RENDER_WAIT = 120          # seconds to wait before re-trying a failed render


def stage_auto():
    """Fully automatic: generate -> render -> publish to YouTube, no approval gate.

    NO-SKIP GUARANTEE: the episode counter is advanced ONLY after the episode is
    fully published with a thumbnail. If the render or upload fails, we retry the
    SAME episode (after a wait) and never move on — so episodes can't be skipped.
    Every published episode is guaranteed to carry a thumbnail."""
    import time
    from src import story
    spec = story.next_episode_spec()
    data = generate_script.generate_episode(spec)       # gen_json retries internally
    slug = data["slug"]; out = _dir(slug)
    _save_state(slug, {"slug": slug, "id": data["id"]})

    final = os.path.join(out, "final.mp4")
    thumb = os.path.join(out, "thumbnail.jpg")

    # ---- render + thumbnail, with retries; do NOT advance the counter unless this works
    last = None
    for attempt in range(1, RENDER_TRIES + 1):
        try:
            generate_voice.make_voice(out, data.get("voice_map", {}))
            generate_visuals.make_visuals(data["scene_prompts"], out)
            render_video.render(out)
            make_thumbnail.make(out)
            if not os.path.exists(final):
                raise RuntimeError("final.mp4 missing after render")
            if not os.path.exists(thumb):                       # thumbnail is mandatory
                raise RuntimeError("thumbnail.jpg missing after render")
            break
        except Exception as e:
            last = e
            print(f"[auto] render attempt {attempt}/{RENDER_TRIES} failed for {slug}: {e}")
            if attempt < RENDER_TRIES:
                print(f"[auto] waiting {RENDER_WAIT}s then retrying (NOT advancing episode)")
                time.sleep(RENDER_WAIT)
    else:
        # every attempt failed -> raise so the counter stays put; the next run retries THIS episode
        raise RuntimeError(f"render failed for {slug} after {RENDER_TRIES} tries: {last}")

    # ---- publish the full episode (thumbnail guaranteed to exist on disk)
    yt = upload_youtube.upload(out)                      # full video + thumbnail + disclaimer
    _save_state(slug, {"slug": slug, "id": data["id"], "youtube": yt})

    # ---- clips to Drive (best-effort; does not gate the episode)
    clip_links = []
    try:
        clip_for_tiktok.clip_video(final)
        folder = upload_drive.ensure_folder(slug, ROOT_FOLDER)
        for clip in sorted(glob.glob(os.path.join(out, "tiktok_part*.mp4"))):
            up = upload_drive.upload(clip, folder, os.path.basename(clip))
            clip_links.append(up.get("link", ""))
    except Exception as e:
        print(f"[auto] clip/drive step skipped: {e}")

    # ---- SUCCESS: only now advance the counter so a failed publish never skips an episode
    story.save_recap(data.get("recap_for_next", ""))
    try:
        rows = _rows(); _set_status(rows, data.get("id", slug), "posted")
    except Exception:
        pass

    clips_txt = ("  |  ".join(f"<{l}|clip {i+1}>" for i, l in enumerate(clip_links))
                 if clip_links else "(clips skipped)")
    slack_blocks._post([{"type": "section", "text": {"type": "mrkdwn",
        "text": (f":rocket: *Auto-published:* {data.get('youtube_title', slug)}\n"
                 f"https://youtu.be/{yt}\nTikTok clips (Drive): {clips_txt}")}}])
    print(f"::notice::auto-published {slug} -> https://youtu.be/{yt}")


def stage_reset():
    """Wipe the serialized-story counter so the next run starts a brand-new Story 1
    from Episode 1. (Old outputs/ dirs are left alone — they're harmless.)"""
    import src.story as story
    if os.path.exists(story.STATE):
        os.remove(story.STATE)
        print(f"[reset] removed {story.STATE} — next episode will be a fresh Story 1, Ep 1")
    else:
        print("[reset] no story_state.json — already clean")


def stage_backfill(count=None):
    """Render + publish a whole story IN ORDER in a single run. stage_auto advances
    the counter only on success, so this can't skip episodes; if one episode fails
    its retries, the loop STOPS (the next run resumes from the same episode)."""
    target = int(count) if count else config.EPISODES_PER_STORY
    done = 0
    while done < target:
        print(f"::group::backfill episode {done + 1}/{target}")
        stage_auto()                 # raises on persistent failure -> loop stops, no skip
        done += 1
        print("::endgroup::")
    print(f"::notice::backfill complete — {done} episode(s) posted in order")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["auto", "backfill", "reset",
                                     "script", "render", "publish"])
    p.add_argument("--episode")
    p.add_argument("--count")
    a = p.parse_args()
    if a.stage == "auto":
        stage_auto()
    elif a.stage == "backfill":
        stage_backfill(a.count)
    elif a.stage == "reset":
        stage_reset()
    elif a.stage == "script":
        stage_script()
    elif a.stage == "render":
        stage_render(a.episode)
    else:
        stage_publish(a.episode)


if __name__ == "__main__":
    main()
