"""
Stage 3c — Image-to-video via Google Veo 3.1 (FREE tier via Google AI Studio).

Each scene image is animated into a short cinematic clip (up to 8 seconds).
Clips are saved as scene_1.mp4 … scene_N.mp4 in out_dir.

Requirements:
  - GEMINI_API_KEY in .env  (get one free at https://aistudio.google.com/apikey)
  - pip install google-genai

Free tier limits (as of 2026):
  - 8 seconds max per clip
  - Rate-limited (not hard-capped monthly via API)
  - 720p output
  - No watermark

Usage:
  python src/generate_veo.py outputs/s1p01-the-quiet-house/
"""
from __future__ import annotations
import os, sys, time, json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _get_client():
    try:
        from google import genai
    except ImportError:
        raise RuntimeError(
            "google-genai not installed. Run: pip install google-genai --break-system-packages")
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/apikey "
            "and add it to .env and as a GitHub Actions secret.")
    return genai.Client(api_key=key)


def animate(scene_prompts: list[str], out_dir: str) -> list[str]:
    """Animate each scene image into a short video clip using Veo 3.1.

    Args:
        scene_prompts: list of shot prompt strings (already have char refs injected)
        out_dir: directory containing scene_N.jpg files; clips saved here as scene_N.mp4

    Returns:
        list of saved .mp4 paths in order
    """
    from google import genai
    from google.genai import types

    client = _get_client()
    clip_paths = []

    for i, prompt in enumerate(scene_prompts, 1):
        out_path = os.path.join(out_dir, f"scene_{i}.mp4")
        img_path = os.path.join(out_dir, f"scene_{i}.jpg")

        if os.path.exists(out_path):
            print(f"[veo] scene {i} clip already exists, skipping")
            clip_paths.append(out_path)
            continue

        if not os.path.exists(img_path):
            raise RuntimeError(f"Image not found for scene {i}: {img_path} — run generate_visuals first")

        with open(img_path, "rb") as f:
            img_bytes = f.read()

        # Motion prompt: cinematic motion + original shot description
        motion_prompt = f"{config.VEO_MOTION}. Scene: {prompt[:300]}"

        print(f"[veo] scene {i}/{len(scene_prompts)} — submitting to Veo...")
        operation = client.models.generate_videos(
            model=config.VEO_MODEL,
            prompt=motion_prompt,
            image=types.Image(image_bytes=img_bytes, mime_type="image/jpeg"),
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9",
                duration_seconds=config.VEO_CLIP_SECONDS,
                number_of_videos=1,
                resolution="720p",
                person_generation="allow_adult",
            ),
        )

        # Poll until done — Veo is async
        attempts = 0
        while not operation.done:
            attempts += 1
            wait = min(10 * attempts, 60)
            print(f"[veo] scene {i} — waiting ({attempts}x, {wait}s)…")
            time.sleep(wait)
            operation = client.operations.get(operation)
            if attempts > 30:
                raise RuntimeError(f"Veo timed out on scene {i} after {attempts} polls")

        generated = operation.response.generated_videos
        if not generated:
            raise RuntimeError(f"Veo returned no video for scene {i}")

        # Download the video bytes
        video = generated[0].video
        client.files.download(file=video)
        with open(out_path, "wb") as f:
            f.write(video.video_bytes)

        print(f"[veo] scene {i} -> {out_path}")
        clip_paths.append(out_path)
        time.sleep(2)   # small pause between submissions to respect rate limits

    return clip_paths


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/generate_veo.py <out_dir>")
        sys.exit(1)
    d = sys.argv[1]
    script = json.load(open(os.path.join(d, "script.json")))
    animate(script["scene_prompts"], d)
