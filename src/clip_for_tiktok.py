"""
Stage 5 — Clip the YouTube video into 3 vertical TikTok parts.

Takes the rendered long-form/full video, splits it into N equal parts (with a
small overlap so each cut feels intentional), forces 9:16, burns a "PART x" label
plus a CTA, and writes a posting plan that schedules the parts to morning /
afternoon / evening.

Requires ffmpeg on the machine (preinstalled on the GitHub Actions ubuntu runner;
`brew install ffmpeg` or `apt install ffmpeg` locally).

Usage:
  python src/clip_for_tiktok.py outputs/1-the-note-on-the-windshield/final.mp4
"""
import os, sys, json, subprocess, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _duration(path: str) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nk=1:nw=1", path,
    ])
    return float(out.strip())


def _ffescape(text: str) -> str:
    return text.replace(":", r"\:").replace("'", r"\'")


def clip_video(video_path: str) -> dict:
    n = config.TIKTOK_CLIPS_PER_VIDEO
    total = _duration(video_path)
    part = total / n
    out_dir = os.path.dirname(video_path)
    clips = []

    for i in range(n):
        start = max(0.0, i * part - (config.CLIP_OVERLAP_SEC if i else 0))
        length = part + (config.CLIP_OVERLAP_SEC if i else 0)
        label = config.CLIP_LABELS[i] if i < len(config.CLIP_LABELS) else f"PART {i+1}"
        out_path = os.path.join(out_dir, f"tiktok_part{i+1}.mp4")

        # 9:16 crop/scale + burned label (top) and CTA (bottom)
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            f"drawtext=text='{_ffescape(label)}':fontcolor=white:fontsize=64:"
            "x=(w-text_w)/2:y=120:box=1:boxcolor=black@0.5:boxborderw=20,"
            f"drawtext=text='{_ffescape(config.CLIP_CTA)}':fontcolor=0xE8E4D8:fontsize=38:"
            "x=(w-text_w)/2:y=h-160:box=1:boxcolor=black@0.4:boxborderw=14"
        )
        cmd = [
            "ffmpeg", "-y", "-ss", f"{start:.2f}", "-t", f"{length:.2f}",
            "-i", video_path, "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k", out_path,
        ]
        subprocess.run(cmd, check=True)
        clips.append({"part": i + 1, "label": label, "file": out_path})
        print(f"[clip] {out_path}")

    # posting plan: today's three dayparts
    today = datetime.date.today()
    plan = []
    for clip, t in zip(clips, config.TIKTOK_DAYPARTS):
        plan.append({**clip, "post_at": f"{today.isoformat()} {t}", "platform": "tiktok"})
    plan_path = os.path.join(out_dir, "tiktok_posting_plan.json")
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=2)
    print(f"[clip] posting plan -> {plan_path}")
    return {"clips": clips, "plan": plan, "plan_path": plan_path}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python src/clip_for_tiktok.py <video.mp4>"); sys.exit(1)
    clip_video(sys.argv[1])
