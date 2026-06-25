"""
Orchestrator — $0 stack (except pennies/day for Claude scripts).

Stages:
  --script   Generate next Part (story bible + character bible + shot list)
  --render   Voice + images (Pollinations) + video clips (Veo 3.1) + FFmpeg assembly
  --preview  Open the assembled Part in the system video player (local review)
  --publish  Upload to YouTube + make 3 TikTok/Shorts teaser clips

Workflow for manual approval:
  python src/run_pipeline.py --script
  # review outputs/<slug>/script.txt
  python src/run_pipeline.py --render <slug>
  # watch outputs/<slug>/final.mp4 — or --preview <slug>
  python src/run_pipeline.py --publish <slug>

Or run fully automatic (cloud):
  python cloud/run_stage.py auto
"""
import os, sys, csv, glob, argparse, json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import generate_script, generate_voice, generate_visuals, render_video, clip_for_tiktok, notify, package_post


def read_queue():
    with open(config.QUEUE_FILE, newline="") as f:
        return list(csv.DictReader(f))

def write_queue(rows):
    with open(config.QUEUE_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

def set_status(rows, rid, status):
    for r in rows:
        if r["id"] == rid: r["status"] = status
    write_queue(rows)

def _dir_for(rid):
    exact = os.path.join(config.OUTPUT_DIR, rid)
    if os.path.isdir(exact):
        return exact
    hits = glob.glob(os.path.join(config.OUTPUT_DIR, f"{rid}*"))
    return hits[0] if hits else None


def cmd_script():
    """Generate the next Part's script, character bible, and shot list."""
    from src import story
    spec = story.next_part_spec()
    data = generate_script.generate_part(spec)
    story.save_recap(data.get("recap_for_next", ""))
    notify.script_ready(data["id"], data)
    slug = data["slug"]
    print(f"\n{'='*60}")
    print(f"PART GENERATED: {data['title']}")
    print(f"  Script:  outputs/{slug}/script.txt")
    print(f"  Shots:   {len(data.get('scene_prompts', []))} shots planned")
    print(f"  Words:   ~{len(data['narration'].split())} words (~5–6 min)")
    print(f"\n>>> Review script.txt, then run:  --render {slug}")
    print(f"{'='*60}\n")


def cmd_render(rid):
    """Generate images + Veo clips + assemble final.mp4 for one Part."""
    out = _dir_for(rid)
    if not out:
        print(f"No script for '{rid}'. Run --script first."); return

    script = json.load(open(os.path.join(out, "script.json")))

    # Stage 1: voice
    print("[pipeline] Stage 1/4 — generating voice...")
    generate_voice.make_voice(out, script.get("voice_map", {}))

    # Stage 2: images (Pollinations — free, character descriptions already in prompts)
    print("[pipeline] Stage 2/4 — generating shot images (Pollinations.ai)...")
    generate_visuals.make_visuals(script["scene_prompts"], out)

    # Stage 3: video clips (Veo 3.1 — free, image-to-video)
    if config.VIDEO_MODE == "veo":
        print("[pipeline] Stage 3/4 — animating shots (Google Veo 3.1)...")
        from src import generate_veo
        generate_veo.animate(script["scene_prompts"], out)
    elif config.VIDEO_MODE == "ai":
        print("[pipeline] Stage 3/4 — animating shots (fal.ai)...")
        from src import generate_ai_video
        generate_ai_video.animate(script["scene_prompts"], out)
    elif config.VIDEO_MODE == "runpod":
        print("[pipeline] Stage 3/4 — animating shots (RunPod)...")
        from src import generate_runpod_video
        generate_runpod_video.animate(script["scene_prompts"], out)
    else:
        print("[pipeline] Stage 3/4 — VIDEO_MODE=stills (Ken-Burns zoom, no Veo)")

    # Stage 4: FFmpeg assembly
    print("[pipeline] Stage 4/4 — assembling final video (FFmpeg)...")
    final = render_video.render(out)

    print(f"\n{'='*60}")
    print(f"RENDER COMPLETE: {final}")
    print(f"\n>>> Watch the video, then run:  --publish {rid}")
    print(f"  Or preview now:              --preview {rid}")
    print(f"{'='*60}\n")


def cmd_preview(rid):
    """Open the assembled Part in the system video player."""
    out = _dir_for(rid)
    if not out:
        print(f"No render for '{rid}'."); return
    final = os.path.join(out, "final.mp4")
    if not os.path.exists(final):
        print(f"No final.mp4 in {out}. Run --render first."); return
    import subprocess, platform
    opener = "open" if platform.system() == "Darwin" else ("xdg-open" if platform.system() == "Linux" else "start")
    subprocess.Popen([opener, final])
    print(f"[preview] opening {final}")


def cmd_publish(rid):
    """Upload to YouTube + cut 3 TikTok teaser clips."""
    out = _dir_for(rid)
    if not out:
        print(f"No render for '{rid}'."); return

    yt_id = None
    client_secret = os.path.join(os.path.dirname(__file__), "..", "client_secret.json")
    if os.path.exists(client_secret):
        from src import upload_youtube
        yt_id = upload_youtube.upload(out)
    else:
        print("[publish] no client_secret.json — skipping YouTube upload (upload final.mp4 manually)")

    clip_for_tiktok.clip_video(os.path.join(out, "final.mp4"))
    dest = package_post.package(out)
    notify.published(rid, yt_id, dest)
    print(f"\n>>> Done. Post kit in {dest}/POST_KIT.md")


def main():
    p = argparse.ArgumentParser(description="Lights Out Tales pipeline")
    p.add_argument("--script",  action="store_true", help="Generate next Part")
    p.add_argument("--render",  metavar="SLUG", help="Render images + video for a Part")
    p.add_argument("--preview", metavar="SLUG", help="Open final.mp4 in video player")
    p.add_argument("--publish", metavar="SLUG", help="Upload to YouTube + cut clips")
    a = p.parse_args()

    if a.render:   cmd_render(a.render)
    elif a.preview: cmd_preview(a.preview)
    elif a.publish: cmd_publish(a.publish)
    else:          cmd_script()


if __name__ == "__main__":
    main()
