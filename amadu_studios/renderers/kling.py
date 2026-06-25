"""
Amadu Studios — Kling Direct API Renderer
Image-to-video via Kling AI's own REST API (not fal.ai middleman).

Cost:  Standard 5s clip ≈ $0.14  |  Pro 5s clip ≈ $0.28
Quality: Significantly better motion coherence than Pollinations Ken-Burns.
API:   https://platform.klingai.com

Setup:
  1. Sign up at platform.klingai.com
  2. Create API key in Settings > API Keys
  3. Add to .env:   KLING_API_KEY=your_key_here
  4. In config.py:  VIDEO_MODE = "kling"  OR
     Per-run:       VIDEO_PROVIDER=kling python amadu_studios/run.py --part 1

Models:
  - kling-v1        standard quality
  - kling-v1-5      improved motion, still cheap
  - kling-v2        best quality, higher cost

FIX vs fal.py:
  - Correct Kling API endpoint and auth scheme (Bearer JWT, not fal.ai Key format)
  - Uses 'duration' as integer, not string
  - Handles Kling-specific polling: GET /v1/videos/image2video/{task_id}
"""
from __future__ import annotations
import os, time, base64, requests

from amadu_studios.renderers.pollinations import PollinationsRenderer
from amadu_studios.database import db
import config

KLING_API_BASE = "https://api.klingai.com"
DEFAULT_MODEL  = "kling-v1-5"
DEFAULT_MODE   = "std"   # std | pro


class KlingRenderer(PollinationsRenderer):
    """
    Kling for video, Pollinations for images.
    Inherits render_image() from PollinationsRenderer (free images).
    """
    name = "kling"

    def __init__(self, model: str = None, mode: str = DEFAULT_MODE):
        self.model = model or getattr(config, "KLING_MODEL", DEFAULT_MODEL)
        self.mode  = mode

    @property
    def supports_video(self) -> bool:
        return True

    def _get_key(self) -> str:
        key = os.environ.get("KLING_API_KEY", "")
        if not key:
            raise RuntimeError(
                "KLING_API_KEY not set.\n"
                "  1. Sign up at platform.klingai.com\n"
                "  2. Create API key in Settings > API Keys\n"
                "  3. Add KLING_API_KEY=your_key to .env"
            )
        return key

    def render_video(self, shot_id: int, image_path: str, prompt: str,
                     out_dir: str, seconds: int = 5) -> str:
        out_path = os.path.join(out_dir, f"shot_{shot_id}.mp4")
        if os.path.exists(out_path):
            return out_path

        key = self._get_key()
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type":  "application/json",
        }

        # Encode image as base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        motion_prompt = getattr(config, "AI_MOTION", "slow cinematic push, horror atmosphere")
        full_prompt   = f"{motion_prompt}. {prompt[:200]}"

        payload = {
            "model":         self.model,
            "mode":          self.mode,
            "image":         img_b64,
            "prompt":        full_prompt,
            "duration":      seconds,
            "aspect_ratio":  "16:9",
            "cfg_scale":     0.5,
        }

        # Submit task
        r = requests.post(
            f"{KLING_API_BASE}/v1/videos/image2video",
            headers=headers, json=payload, timeout=30)

        if r.status_code == 401:
            raise RuntimeError("KLING_API_KEY invalid or expired — check platform.klingai.com")
        r.raise_for_status()
        resp    = r.json()
        task_id = resp.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"Kling returned no task_id: {resp}")

        print(f"[kling] shot {shot_id} task submitted: {task_id}")

        # Poll for completion
        for attempt in range(90):   # max 15 min
            time.sleep(10)
            poll = requests.get(
                f"{KLING_API_BASE}/v1/videos/image2video/{task_id}",
                headers=headers, timeout=30)
            poll.raise_for_status()
            data   = poll.json().get("data", {})
            status = data.get("task_status", "")

            if status == "succeed":
                works = data.get("task_result", {}).get("videos", [])
                if not works:
                    raise RuntimeError(f"Kling succeed but no videos: {data}")
                video_url = works[0].get("url")
                break
            elif status in ("failed", "cancelled"):
                raise RuntimeError(f"Kling task {task_id} {status}: {data.get('task_status_msg')}")
            # processing / waiting — keep polling
        else:
            raise RuntimeError(f"Kling timed out on shot {shot_id} after 15 min")

        # Download
        os.makedirs(out_dir, exist_ok=True)
        vid_bytes = requests.get(video_url, timeout=120).content
        with open(out_path, "wb") as f:
            f.write(vid_bytes)

        db.update_shot(shot_id, video_path=out_path, render_status="video_done")
        db.log_render(shot_id, self.name, 1, "success", out_path)
        print(f"[kling] shot {shot_id} video -> {out_path}")
        return out_path
