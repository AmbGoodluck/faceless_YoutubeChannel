"""
Amadu Studios — fal.ai Renderer (PAID)
Image-to-video via Kling on fal.ai (~$0.05/clip = ~$1/part).
Requires FAL_KEY in .env. Drop-in replacement for PollinationsRenderer.

To activate: set VIDEO_MODE = "fal" in config.py and add FAL_KEY to .env
"""
from __future__ import annotations
import os, time, requests

from amadu_studios.renderers.pollinations import PollinationsRenderer
from amadu_studios.database import db
import config


class FalRenderer(PollinationsRenderer):
    """
    Uses Pollinations for images (free) + fal.ai Kling for video (paid).
    Inherits render_image() from PollinationsRenderer.
    """
    name = "fal"

    @property
    def supports_video(self) -> bool:
        return True

    def render_video(self, shot_id: int, image_path: str, prompt: str,
                     out_dir: str, seconds: int = 5) -> str:
        out_path = os.path.join(out_dir, f"shot_{shot_id}.mp4")
        if os.path.exists(out_path):
            return out_path

        key = os.environ.get("FAL_KEY")
        if not key:
            raise RuntimeError("FAL_KEY not set — add it to .env to use fal.ai video")

        import base64
        with open(image_path, "rb") as f:
            img_b64 = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()

        motion = config.AI_MOTION + ". " + prompt[:200]
        headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}

        # Submit
        r = requests.post(
            f"{config.FAL_QUEUE_BASE}/{config.FAL_MODEL}",
            headers=headers,
            json={"image_url": img_b64, "prompt": motion,
                  "duration": str(seconds), "aspect_ratio": "16:9"},
            timeout=30)
        r.raise_for_status()
        req_id = r.json().get("request_id")

        # Poll
        for _ in range(60):
            time.sleep(10)
            status = requests.get(
                f"{config.FAL_QUEUE_BASE}/{config.FAL_MODEL}/requests/{req_id}/status",
                headers=headers, timeout=30).json()
            if status.get("status") == "COMPLETED":
                break
        else:
            raise RuntimeError(f"fal.ai timed out on shot {shot_id}")

        # Download
        result = requests.get(
            f"{config.FAL_QUEUE_BASE}/{config.FAL_MODEL}/requests/{req_id}",
            headers=headers, timeout=30).json()
        video_url = result.get("video", {}).get("url")
        if not video_url:
            raise RuntimeError(f"fal.ai returned no video URL for shot {shot_id}")

        os.makedirs(out_dir, exist_ok=True)
        vid_data = requests.get(video_url, timeout=120).content
        with open(out_path, "wb") as f:
            f.write(vid_data)

        db.update_shot(shot_id, video_path=out_path, render_status="video_done")
        db.log_render(shot_id, self.name, 1, "success", out_path)
        print(f"[fal] shot {shot_id} video -> {out_path}")
        return out_path
