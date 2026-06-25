"""
Amadu Studios — Replicate Renderer
Wraps multiple open-source video models via Replicate's pay-per-run API.

Cost:   Wan2.1  ~$0.02-0.04/clip  |  CogVideoX ~$0.03-0.06/clip
API:    https://replicate.com/docs/reference/http
Key:    REPLICATE_API_TOKEN from replicate.com/account/api-tokens

Models supported:
  - wan      : Wan2.1 image-to-video (Alibaba open-source, strong motion)
  - cogvideo : CogVideoX-5b (Zhipu AI, open-source, great quality)
  - ltx      : LTX-Video (Lightricks, fast + cheap)
  - stable   : stable-video-diffusion (Stability AI classic)
  - hunyuan  : HunyuanVideo (Tencent, SOTA quality, slow)

Setup:
  1. Create account at replicate.com
  2. Get token: replicate.com/account/api-tokens
  3. Add to .env:   REPLICATE_API_TOKEN=r8_xxxxx
  4. In config.py:  VIDEO_MODE = "replicate"
     Optionally:    REPLICATE_MODEL = "wan"  (default)

OR per-run:
  VIDEO_PROVIDER=replicate REPLICATE_MODEL=cogvideo python amadu_studios/run.py --part 1
"""
from __future__ import annotations
import os, time, base64, io, requests

from amadu_studios.renderers.pollinations import PollinationsRenderer
from amadu_studios.database import db
import config

REPLICATE_API = "https://api.replicate.com/v1"

# Replicate model slugs (owner/model:version — version can be omitted for latest)
MODELS = {
    "wan": {
        "id":          "wavespeed-ai/wan-2.1-i2v-480p",
        "image_field": "image",
        "prompt_field": "prompt",
        "duration_field": None,        # wan uses num_frames
        "frames_per_sec": 16,
        "extra": {"num_frames": 81, "sample_steps": 20, "fps": 16},
    },
    "cogvideo": {
        "id":          "zsxkib/cogvideox-5b",
        "image_field": "image",
        "prompt_field": "prompt",
        "duration_field": None,
        "frames_per_sec": 8,
        "extra": {"num_frames": 49, "guidance_scale": 6},
    },
    "ltx": {
        "id":          "lightricks/ltx-video",
        "image_field": "image",
        "prompt_field": "prompt",
        "duration_field": "duration",
        "frames_per_sec": 25,
        "extra": {"num_inference_steps": 40, "guidance_scale": 3},
    },
    "stable": {
        "id":          "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
        "image_field": "input_image",
        "prompt_field": None,          # SVD is image-only, no prompt
        "duration_field": "video_length",
        "frames_per_sec": 6,
        "extra": {"sizing_strategy": "maintain_aspect_ratio", "motion_bucket_id": 40},
    },
    "hunyuan": {
        "id":          "tencent/hunyuan-video",
        "image_field": "image",
        "prompt_field": "prompt",
        "duration_field": None,
        "frames_per_sec": 24,
        "extra": {"num_frames": 129, "steps": 50},
    },
}

DEFAULT_MODEL = "wan"


class ReplicateRenderer(PollinationsRenderer):
    """
    Open-source video via Replicate. Uses Pollinations for images (free).
    Choose model via REPLICATE_MODEL env var or config.REPLICATE_MODEL.
    """
    name = "replicate"

    def __init__(self, model_key: str = None):
        self.model_key = (
            model_key
            or os.environ.get("REPLICATE_MODEL")
            or getattr(config, "REPLICATE_MODEL", DEFAULT_MODEL)
        )
        if self.model_key not in MODELS:
            print(f"[replicate] unknown model '{self.model_key}', falling back to '{DEFAULT_MODEL}'")
            self.model_key = DEFAULT_MODEL
        self.model_cfg = MODELS[self.model_key]

    @property
    def supports_video(self) -> bool:
        return True

    def _get_token(self) -> str:
        tok = os.environ.get("REPLICATE_API_TOKEN", "")
        if not tok:
            raise RuntimeError(
                "REPLICATE_API_TOKEN not set.\n"
                "  1. Sign up at replicate.com\n"
                "  2. Get token: replicate.com/account/api-tokens\n"
                "  3. Add REPLICATE_API_TOKEN=r8_xxxxx to .env"
            )
        return tok

    def render_video(self, shot_id: int, image_path: str, prompt: str,
                     out_dir: str, seconds: int = 5) -> str:
        out_path = os.path.join(out_dir, f"shot_{shot_id}.mp4")
        if os.path.exists(out_path):
            return out_path

        token   = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Prefer":        "wait",
        }
        cfg_m = self.model_cfg

        # Encode image as data URI (Replicate accepts base64 data URIs)
        with open(image_path, "rb") as f:
            img_b64 = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()

        motion = getattr(config, "AI_MOTION", "slow cinematic camera, horror atmosphere")
        full_prompt = f"{motion}. {prompt[:200]}"

        inp: dict = dict(cfg_m.get("extra", {}))
        inp[cfg_m["image_field"]] = img_b64

        if cfg_m["prompt_field"]:
            inp[cfg_m["prompt_field"]] = full_prompt

        if cfg_m["duration_field"]:
            inp[cfg_m["duration_field"]] = seconds

        payload = {"input": inp}

        # Submit prediction
        r = requests.post(
            f"{REPLICATE_API}/models/{cfg_m['id']}/predictions",
            headers=headers, json=payload, timeout=30)
        if r.status_code == 401:
            raise RuntimeError("REPLICATE_API_TOKEN invalid — check replicate.com/account")
        r.raise_for_status()
        pred = r.json()
        pred_id = pred.get("id")
        if not pred_id:
            raise RuntimeError(f"Replicate returned no prediction id: {pred}")

        print(f"[replicate/{self.model_key}] shot {shot_id} prediction: {pred_id}")

        # Poll
        poll_url = f"{REPLICATE_API}/predictions/{pred_id}"
        for attempt in range(120):   # max 20 min
            time.sleep(10)
            r = requests.get(poll_url, headers=headers, timeout=30)
            r.raise_for_status()
            data   = r.json()
            status = data.get("status", "")

            if status == "succeeded":
                output = data.get("output")
                # Output is usually a URL or list of URLs
                if isinstance(output, list):
                    video_url = output[0]
                elif isinstance(output, str):
                    video_url = output
                else:
                    raise RuntimeError(f"Unexpected output format: {output}")
                break
            elif status in ("failed", "canceled"):
                err = data.get("error", "no error message")
                raise RuntimeError(f"Replicate prediction {pred_id} {status}: {err}")
        else:
            raise RuntimeError(f"Replicate timed out on shot {shot_id} (20 min)")

        # Download
        os.makedirs(out_dir, exist_ok=True)
        vid_bytes = requests.get(video_url, timeout=120).content
        with open(out_path, "wb") as f:
            f.write(vid_bytes)

        db.update_shot(shot_id, video_path=out_path, render_status="video_done")
        db.log_render(shot_id, self.name, 1, "success", out_path)
        print(f"[replicate/{self.model_key}] shot {shot_id} video -> {out_path}")
        return out_path
