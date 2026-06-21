"""
Stage 3c — Animate each scene image into a short AI video clip via fal.ai
(image-to-video). Keeps your character consistent (the image defines them) and adds
real motion. PAID: ~$0.05-0.50 per clip depending on the model.

Setup: get a key at https://fal.ai/dashboard/keys  -> put FAL_KEY in .env / GitHub secret.
Confirm the exact input fields for your chosen model on its fal page
(config.FAL_MODEL) — some models name the duration field differently or omit it.

Produces: <out_dir>/scene_1.mp4 ... scene_N.mp4
"""
from __future__ import annotations
import os, sys, time, base64, requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _data_uri(path: str) -> str:
    b = base64.b64encode(open(path, "rb").read()).decode()
    return f"data:image/jpeg;base64,{b}"


def _headers():
    return {"Authorization": f"Key {os.environ['FAL_KEY']}", "Content-Type": "application/json"}


def _one(image_path: str, motion_prompt: str, out_path: str):
    body = {
        "image_url": _data_uri(image_path),
        "prompt": motion_prompt,
        "duration": str(config.AI_CLIP_SECONDS),   # some models want an int or omit this
    }
    sub = requests.post(f"{config.FAL_QUEUE_BASE}/{config.FAL_MODEL}",
                        json=body, headers=_headers(), timeout=60)
    sub.raise_for_status()
    j = sub.json()
    status_url, response_url = j["status_url"], j["response_url"]

    waited = 0
    while waited < 600:                              # up to 10 min per clip
        st = requests.get(status_url, headers=_headers(), timeout=30).json()
        s = str(st.get("status", "")).upper()
        if s == "COMPLETED":
            break
        if s in ("FAILED", "ERROR"):
            raise RuntimeError(f"fal job failed: {st}")
        time.sleep(6); waited += 6
    else:
        raise TimeoutError("fal job timed out")

    res = requests.get(response_url, headers=_headers(), timeout=60).json()
    video_url = res.get("video", {}).get("url") or res.get("video_url")
    if not video_url:
        raise RuntimeError(f"no video in fal result: {res}")
    vid = requests.get(video_url, timeout=180); vid.raise_for_status()
    open(out_path, "wb").write(vid.content)


def animate(scene_prompts: list, out_dir: str) -> list:
    import glob
    imgs = sorted(glob.glob(os.path.join(out_dir, "scene_*.jpg")))
    out = []
    for i, img in enumerate(imgs, 1):
        prompt = (scene_prompts[i - 1] if i - 1 < len(scene_prompts) else "") + ", " + config.AI_MOTION
        dest = os.path.join(out_dir, f"scene_{i}.mp4")
        for attempt in range(2):
            try:
                _one(img, prompt, dest)
                out.append(dest)
                print(f"[ai-video] scene {i} -> {dest}")
                break
            except Exception as e:
                print(f"[ai-video] scene {i} attempt {attempt+1} failed: {e}")
                time.sleep(8)
        else:
            raise RuntimeError(f"fal image-to-video failed for scene {i}")
    return out


if __name__ == "__main__":
    import json
    d = sys.argv[1]
    s = json.load(open(os.path.join(d, "script.json")))
    animate(s["scene_prompts"], d)
