"""
Orchestrator — $0 stack, runs one episode through the pipeline.

Stages:
  queued
    --script   generate_script (Gemini)        -> script_ready  [YOU APPROVE script.txt]
    --render   voice + visuals + assemble       -> rendered      [YOU APPROVE final.mp4]
    --publish  upload to YouTube + clip 3 parts  -> posted

Nothing publishes without your two approvals (YouTube authenticity rule).

Usage:
  python src/run_pipeline.py --script            # next queued -> script (stops for review)
  python src/run_pipeline.py --render 1          # approved script id -> full video (stops for review)
  python src/run_pipeline.py --publish 1         # upload to YouTube + make 3 TikTok clips
"""
import os, sys, csv, glob, argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import generate_script, generate_voice, generate_visuals, render_video, clip_for_tiktok


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
    hits = glob.glob(os.path.join(config.OUTPUT_DIR, f"{rid}-*"))
    return hits[0] if hits else None


def cmd_script(rows):
    row = next((r for r in rows if r["status"] == "queued"), None)
    if not row:
        print("Queue empty — add rows to content_queue.csv."); return
    generate_script.generate(row)
    set_status(rows, row["id"], "script_ready")
    print(f"\n>>> CHECKPOINT 1: read outputs/{row['id']}-*/script.txt, then --render {row['id']}")


def cmd_render(rows, rid):
    out = _dir_for(rid)
    if not out: print(f"No script for id {rid}; run --script."); return
    import json
    script = json.load(open(os.path.join(out, "script.json")))
    generate_voice.make_voice(script["narration"], out)
    generate_visuals.make_visuals(script["scene_prompts"], out)
    render_video.render(out)
    set_status(rows, rid, "rendered")
    print(f"\n>>> CHECKPOINT 2: watch {out}/final.mp4, then --publish {rid}")


def cmd_publish(rows, rid):
    out = _dir_for(rid)
    if not out: print(f"No render for id {rid}."); return
    # YouTube upload (optional — skip if client_secret.json absent)
    if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "client_secret.json")):
        from src import upload_youtube
        upload_youtube.upload(out)
        set_status(rows, rid, "uploaded")
    else:
        print("[publish] no client_secret.json — skipping YouTube upload (upload final.mp4 by hand)")
    # Always make the 3 TikTok clips + posting plan
    clip_for_tiktok.clip_video(os.path.join(out, "final.mp4"))
    set_status(rows, rid, "clipped")
    print(f"\n>>> Done. Schedule {out}/tiktok_part1..3.mp4 to TikTok at "
          f"{', '.join(config.TIKTOK_DAYPARTS)} (see tiktok_posting_plan.json).")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--script", action="store_true")
    p.add_argument("--render", metavar="ID")
    p.add_argument("--publish", metavar="ID")
    a = p.parse_args()
    rows = read_queue()
    if a.render: cmd_render(rows, a.render)
    elif a.publish: cmd_publish(rows, a.publish)
    else: cmd_script(rows)


if __name__ == "__main__":
    main()
