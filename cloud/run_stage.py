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
    narration = generate_script.load_narration(out)
    generate_voice.make_voice(narration, out)
    generate_visuals.make_visuals(script["scene_prompts"], out)
    if config.VIDEO_MODE == "ai":
        from src import generate_ai_video
        generate_ai_video.animate(script["scene_prompts"], out)
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["script", "render", "publish"])
    p.add_argument("--episode")
    a = p.parse_args()
    if a.stage == "script":
        stage_script()
    elif a.stage == "render":
        stage_render(a.episode)
    else:
        stage_publish(a.episode)


if __name__ == "__main__":
    main()
