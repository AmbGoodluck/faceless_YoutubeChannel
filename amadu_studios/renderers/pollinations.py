"""
Amadu Studios — Pollinations Renderer
Free image generation via Pollinations.ai (no API key).
Ken-Burns zoom for video (also free, FFmpeg-based).
"""
from __future__ import annotations
import os, time, urllib.parse, requests, subprocess

from amadu_studios.renderers.base import BaseRenderer
from amadu_studios.database import db
import config


class PollinationsRenderer(BaseRenderer):
    name = "pollinations"

    def render_image(self, shot_id: int, prompt: str, out_dir: str,
                     width: int = 1920, height: int = 1080,
                     seed: int = None) -> str:
        out_path = os.path.join(out_dir, f"shot_{shot_id}.jpg")
        if os.path.exists(out_path):
            print(f"[pollinations] shot {shot_id} image cached, skipping")
            return out_path

        # Use caller-supplied seed (for character/location consistency) or
        # fall back to per-shot seed (guarantees variety for non-face shots).
        effective_seed = seed if seed is not None else shot_id * 17

        url = (f"{config.POLLINATIONS_BASE}/{urllib.parse.quote(prompt)}"
               f"?width={width}&height={height}&nologo=true&seed={effective_seed}")

        for attempt in range(3):
            try:
                r = requests.get(url, timeout=120)
                r.raise_for_status()
                os.makedirs(out_dir, exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(r.content)
                db.update_shot(shot_id, image_path=out_path, render_status="image_done")
                db.log_render(shot_id, self.name, attempt+1, "success", out_path)
                print(f"[pollinations] shot {shot_id} -> {out_path}")
                time.sleep(1)
                return out_path
            except Exception as e:
                print(f"[pollinations] shot {shot_id} attempt {attempt+1}/3 failed: {e}")
                db.log_render(shot_id, self.name, attempt+1, "failed", error=str(e))
                time.sleep(5)
        raise RuntimeError(f"Pollinations failed for shot {shot_id} after 3 attempts")

    @property
    def supports_video(self) -> bool:
        return True  # Ken-Burns via FFmpeg

    def render_video(self, shot_id: int, image_path: str, prompt: str,
                     out_dir: str, seconds: int = 6) -> str:
        """Ken-Burns slow zoom — free, no API."""
        out_path = os.path.join(out_dir, f"shot_{shot_id}.mp4")
        if os.path.exists(out_path):
            return out_path

        fps, W, H = 30, config.IMAGE_W, config.IMAGE_H
        frames = fps * seconds
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"zoompan=z='min(zoom+0.0010,1.15)':d={frames}:s={W}x{H}:fps={fps}")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", image_path, "-vf", vf, "-frames:v", str(frames),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), out_path]
        subprocess.run(cmd, check=True)
        db.update_shot(shot_id, video_path=out_path, render_status="video_done")
        print(f"[pollinations] shot {shot_id} Ken-Burns -> {out_path}")
        return out_path
