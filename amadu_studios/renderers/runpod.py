"""
Amadu Studios — RunPod Serverless Renderer
Open-source image-to-video on a rented GPU. Cheapest real-video option.

Cost:  ~$0.20-0.40/part on A40 serverless  (scale-to-zero, pay per second)
API:   https://api.runpod.ai/v2/{endpoint_id}/run
Docs:  https://docs.runpod.io/serverless/overview

Two modes (config.RUNPOD_MODE):
  "simple"  — for pre-built endpoints (e.g. RunPod's official Wan 2.1 I2V template).
              Sends: {"image": base64, "prompt": str, "frames": int}
  "comfyui" — for worker-comfyui endpoints. Injects image + prompt into a
              ComfyUI workflow JSON (export from ComfyUI as API format).
              File: config.RUNPOD_WORKFLOW  (e.g. comfyui_workflows/wan_i2v.json)

Setup (see RENDERERS_SETUP.md for full walkthrough):
  1. Create account at runpod.io
  2. Deploy a serverless endpoint (recommended: Wan 2.1 I2V template, A40 GPU)
  3. Copy the Endpoint ID from the dashboard
  4. Add to .env:
       RUNPOD_API_KEY=your_key_here
  5. Add to config.py (or .env):
       RUNPOD_ENDPOINT_ID=abc123def456
       RUNPOD_MODE=simple
  6. In config.py: VIDEO_MODE = "runpod"
     OR per-run:   VIDEO_PROVIDER=runpod python amadu_studios/run.py --part 1
"""
from __future__ import annotations
import os, time, json, base64, requests

from amadu_studios.renderers.pollinations import PollinationsRenderer
from amadu_studios.database import db
import config


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _extract_video_bytes(output) -> bytes:
    """
    RunPod endpoints return video as base64 string, URL, or nested dict.
    Walk the output structure to find the first video payload.
    Ported from pipeline/src/generate_runpod_video.py with added type safety.
    """
    def walk(o):
        if isinstance(o, str):
            if o.startswith("http"):
                r = requests.get(o, timeout=180)
                r.raise_for_status()
                return r.content
            # base64 with or without data URI prefix
            raw = o.split(",")[-1]
            try:
                return base64.b64decode(raw)
            except Exception:
                return None
        if isinstance(o, dict):
            for k in ("video", "data", "message", "url", "base64", "output"):
                if k in o:
                    result = walk(o[k])
                    if result:
                        return result
            for v in o.values():
                result = walk(v)
                if result:
                    return result
        if isinstance(o, list):
            for v in o:
                result = walk(v)
                if result:
                    return result
        return None

    data = walk(output)
    if not data:
        raise RuntimeError(f"No video found in RunPod output: {str(output)[:400]}")
    return data


def _build_simple_input(image_path: str, prompt: str) -> dict:
    """Input for pre-built 'simple' endpoints (Wan 2.1 I2V, LTX, etc.)"""
    motion = getattr(config, "AI_MOTION", "slow cinematic camera, horror atmosphere")
    return {
        "image":   _b64(image_path),
        "prompt":  f"{prompt[:200]}, {motion}",
        "frames":  getattr(config, "RUNPOD_FRAMES", 97),
    }


def _build_comfyui_input(image_path: str, prompt: str) -> dict:
    """Input for worker-comfyui endpoints — injects into ComfyUI workflow JSON."""
    workflow_path = getattr(config, "RUNPOD_WORKFLOW", "comfyui_workflows/wan_i2v.json")
    if not os.path.exists(workflow_path):
        raise RuntimeError(
            f"ComfyUI workflow file not found: {workflow_path}\n"
            "Export your workflow from ComfyUI as 'Save (API Format)' and save it there."
        )
    wf = json.load(open(workflow_path))
    img_name = os.path.basename(image_path)
    motion   = getattr(config, "AI_MOTION", "slow cinematic camera")
    node_key = getattr(config, "RUNPOD_NODE_PROMPT", "positive")

    for node in wf.values():
        ct    = node.get("class_type", "")
        title = (node.get("_meta", {}) or {}).get("title", "").lower()
        if ct == "LoadImage":
            node.setdefault("inputs", {})["image"] = img_name
        if ct == "CLIPTextEncode" and ("pos" in title or node_key in title):
            node.setdefault("inputs", {})["text"] = f"{prompt[:200]}, {motion}"

    return {
        "workflow": wf,
        "images":   [{"name": img_name, "image": _b64(image_path)}],
    }


class RunPodRenderer(PollinationsRenderer):
    """
    RunPod serverless for video. Pollinations for images (free).
    Inherits render_image() from PollinationsRenderer.
    """
    name = "runpod"

    @property
    def supports_video(self) -> bool:
        return True

    def _get_headers(self) -> dict:
        key = os.environ.get("RUNPOD_API_KEY", "")
        if not key:
            raise RuntimeError(
                "RUNPOD_API_KEY not set.\n"
                "  1. Sign up at runpod.io\n"
                "  2. Settings > API Keys > Create Key\n"
                "  3. Add RUNPOD_API_KEY=your_key to .env"
            )
        return {"Authorization": key, "Content-Type": "application/json"}

    def _get_endpoint(self) -> str:
        ep = getattr(config, "RUNPOD_ENDPOINT_ID", "") or os.environ.get("RUNPOD_ENDPOINT_ID", "")
        if not ep:
            raise RuntimeError(
                "RUNPOD_ENDPOINT_ID not set.\n"
                "  Deploy a serverless endpoint at runpod.io then add:\n"
                "  RUNPOD_ENDPOINT_ID=your_endpoint_id to .env"
            )
        return ep

    def render_video(self, shot_id: int, image_path: str, prompt: str,
                     out_dir: str, seconds: int = 5) -> str:
        out_path = os.path.join(out_dir, f"shot_{shot_id}.mp4")
        if os.path.exists(out_path):
            return out_path

        headers     = self._get_headers()
        endpoint_id = self._get_endpoint()
        base_url    = f"{config.RUNPOD_BASE}/{endpoint_id}"
        mode        = getattr(config, "RUNPOD_MODE", "simple")

        if mode == "comfyui":
            inp = _build_comfyui_input(image_path, prompt)
        else:
            inp = _build_simple_input(image_path, prompt)

        # Submit
        r = requests.post(
            f"{base_url}/run",
            headers=headers,
            json={"input": inp},
            timeout=60)
        if not r.ok:
            raise RuntimeError(f"RunPod submit failed {r.status_code}: {r.text[:300]}")

        job_id = r.json().get("id")
        if not job_id:
            raise RuntimeError(f"RunPod returned no job id: {r.text[:300]}")

        print(f"[runpod] shot {shot_id} job: {job_id}")

        # Poll
        waited = 0
        max_wait = 900  # 15 min
        while waited < max_wait:
            time.sleep(6)
            waited += 6
            status_r = requests.get(f"{base_url}/status/{job_id}",
                                     headers=headers, timeout=30)
            status_r.raise_for_status()
            status_data = status_r.json()
            st = str(status_data.get("status", "")).upper()

            if st == "COMPLETED":
                vid_bytes = _extract_video_bytes(status_data.get("output"))
                os.makedirs(out_dir, exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(vid_bytes)
                db.update_shot(shot_id, video_path=out_path, render_status="video_done")
                db.log_render(shot_id, self.name, 1, "success", out_path)
                print(f"[runpod] shot {shot_id} video -> {out_path}")
                return out_path
            elif st in ("FAILED", "CANCELLED", "TIMED_OUT"):
                err = str(status_data)[:300]
                db.log_render(shot_id, self.name, 1, "failed", error=err)
                raise RuntimeError(f"RunPod job {st}: {err}")
            # IN_QUEUE / IN_PROGRESS — continue polling

        raise TimeoutError(f"RunPod timed out for shot {shot_id} after {max_wait}s")
