"""
Stage 3c (open-source path) — animate each scene image into a video clip using a
RunPod Serverless endpoint running ComfyUI + an image-to-video model (LTX / Wan).

Cheap + scale-to-zero: you only pay for the seconds each job runs (~$0.22/hr GPU).
Two modes (config.RUNPOD_MODE):
  - "comfyui": worker-comfyui — sends a ComfyUI workflow JSON + the image; you export
               the workflow once from ComfyUI ("Save (API Format)") into RUNPOD_WORKFLOW.
  - "simple" : a ready-made endpoint (e.g. RunPod's WAN 2.2 I2V) — sends {image, prompt}.

Env: RUNPOD_API_KEY. See cloud/RUNPOD_SETUP.md.
Produces: <out_dir>/scene_1.mp4 ... scene_N.mp4
"""
from __future__ import annotations
import os, sys, time, json, base64, glob, requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _headers():
    return {"Authorization": os.environ["RUNPOD_API_KEY"], "Content-Type": "application/json"}


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _build_input(image_path: str, prompt: str) -> dict:
    if config.RUNPOD_MODE == "simple":
        return {"image": _b64(image_path), "prompt": f"{prompt}, {config.AI_MOTION}",
                "frames": config.RUNPOD_FRAMES}
    # comfyui mode: inject the image filename + prompt into the exported workflow
    wf = json.load(open(config.RUNPOD_WORKFLOW))
    img_name = os.path.basename(image_path)
    for node in wf.values():
        ct = node.get("class_type", "")
        title = (node.get("_meta", {}) or {}).get("title", "").lower()
        if ct == "LoadImage":
            node.setdefault("inputs", {})["image"] = img_name
        if ct == "CLIPTextEncode" and ("pos" in title or config.RUNPOD_NODE_PROMPT in title):
            node.setdefault("inputs", {})["text"] = f"{prompt}, {config.AI_MOTION}"
    return {"workflow": wf, "images": [{"name": img_name, "image": _b64(image_path)}]}


def _extract_video(output, dest: str) -> str:
    """worker-comfyui/ready endpoints return the clip as base64 or a URL — handle both."""
    def find(o):
        if isinstance(o, str):
            return o
        if isinstance(o, dict):
            for k in ("video", "data", "message", "url", "base64"):
                if k in o:
                    return find(o[k])
            for v in o.values():
                r = find(v)
                if r:
                    return r
        if isinstance(o, list):
            for v in o:
                r = find(v)
                if r:
                    return r
        return None
    val = find(output)
    if not val:
        raise RuntimeError(f"no video found in RunPod output: {str(output)[:300]}")
    if val.startswith("http"):
        r = requests.get(val, timeout=180); r.raise_for_status()
        open(dest, "wb").write(r.content)
    else:
        open(dest, "wb").write(base64.b64decode(val.split(",")[-1]))
    return dest


def _one(image_path: str, prompt: str, out_path: str):
    base = f"{config.RUNPOD_BASE}/{config.RUNPOD_ENDPOINT_ID}"
    r = requests.post(f"{base}/run", json={"input": _build_input(image_path, prompt)},
                      headers=_headers(), timeout=60)
    if not r.ok:
        raise RuntimeError(f"RunPod submit {r.status_code}: {r.text[:300]}")
    jid = r.json()["id"]
    waited = 0
    while waited < 900:
        s = requests.get(f"{base}/status/{jid}", headers=_headers(), timeout=30).json()
        st = str(s.get("status", "")).upper()
        if st == "COMPLETED":
            return _extract_video(s.get("output"), out_path)
        if st in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise RuntimeError(f"RunPod job {st}: {str(s)[:300]}")
        time.sleep(6); waited += 6
    raise TimeoutError("RunPod job timed out")


def animate(scene_prompts: list, out_dir: str) -> list:
    imgs = sorted(glob.glob(os.path.join(out_dir, "scene_*.jpg")))
    out = []
    for i, img in enumerate(imgs, 1):
        prompt = scene_prompts[i - 1] if i - 1 < len(scene_prompts) else ""
        dest = os.path.join(out_dir, f"scene_{i}.mp4")
        for attempt in range(2):
            try:
                _one(img, prompt, dest); out.append(dest)
                print(f"[runpod] scene {i} -> {dest}"); break
            except Exception as e:
                print(f"[runpod] scene {i} attempt {attempt+1} failed: {e}"); time.sleep(8)
        else:
            raise RuntimeError(f"RunPod failed for scene {i}")
    return out


if __name__ == "__main__":
    import json as _j
    d = sys.argv[1]
    animate(_j.load(open(os.path.join(d, "script.json")))["scene_prompts"], d)
