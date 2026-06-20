"""
Packages a finished episode for MANUAL posting:
  - generates the YouTube thumbnail
  - writes POST_KIT.md (title, description, hashtags, pinned comment, per-clip captions)
  - copies the 3 clips + thumbnail + kit into  to_post/<slug>/
  - appends the 3 clips to  to_post/queue.json  (what the daily reminder serves)

Point Google Drive / iCloud at the to_post/ folder and the clips reach your phone.
"""
import os, sys, json, glob, shutil

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import make_thumbnail

TO_POST = "to_post"
QUEUE = os.path.join(TO_POST, "queue.json")


def _load_queue():
    if os.path.exists(QUEUE):
        return json.load(open(QUEUE))
    return []


def _save_queue(q):
    json.dump(q, open(QUEUE, "w"), indent=2)


def package(out_dir: str) -> str:
    script = json.load(open(os.path.join(out_dir, "script.json")))
    slug = os.path.basename(out_dir.rstrip("/"))
    dest = os.path.join(TO_POST, slug)
    os.makedirs(dest, exist_ok=True)

    thumb = make_thumbnail.make(out_dir)
    tags = " ".join("#" + t.lstrip("#") for t in script.get("hashtags", []))
    caption = script.get("tiktok_caption", script.get("title", ""))

    # POST_KIT.md
    kit = [f"# POST KIT — {script.get('title','')}", ""]
    kit += ["## YouTube (long-form)",
            f"**Title:** {script.get('youtube_title','')}", "",
            f"**Description:**\n{script.get('youtube_description','')}", "",
            f"**Thumbnail:** thumbnail.jpg (in this folder)", "",
            f"**Pinned comment:** {script.get('pinned_comment','')}", "",
            f"**Tags:** {tags}", "", "---", "", "## TikTok / YouTube Shorts — 3 clips"]
    clips = sorted(glob.glob(os.path.join(out_dir, "tiktok_part*.mp4")))
    queue = _load_queue()
    for i, clip in enumerate(clips, 1):
        cap = f"{caption} (Part {i}/{len(clips)})\n\n{tags}"
        shutil.copy(clip, os.path.join(dest, os.path.basename(clip)))
        kit += [f"### Part {i}  ({config.TIKTOK_DAYPARTS[i-1] if i-1 < len(config.TIKTOK_DAYPARTS) else ''})",
                f"```\n{cap}\n```", ""]
        queue.append({
            "episode": slug, "part": i, "label": f"Part {i}/{len(clips)}",
            "file": os.path.abspath(os.path.join(dest, os.path.basename(clip))),
            "caption": cap, "posted": False,
        })
    shutil.copy(thumb, os.path.join(dest, "thumbnail.jpg"))
    open(os.path.join(dest, "POST_KIT.md"), "w").write("\n".join(kit))
    _save_queue(queue)
    print(f"[package] {dest}/  (clips + thumbnail + POST_KIT.md), queued 3 clips")
    return dest


if __name__ == "__main__":
    package(sys.argv[1])
