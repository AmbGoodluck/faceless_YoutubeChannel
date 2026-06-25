"""
Stage 3 — Video generation via Revid.ai (Typeframes shares the same API).

Auth: HTTP header  key: <YOUR_REVID_API_KEY>   (Growth plan required)
Rendering is async — Revid sends the finished video to a webhook URL, and/or you
poll the status endpoint with the returned project id.

IMPORTANT: the exact request body changes as Revid adds features. Get the current
parameters by going to https://www.typeframes.com/create , clicking the "..." next
to "Create a new video", and hitting "Get API Code". Paste those params into
build_payload() below.
"""
import os, sys, time, requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _headers():
    return {"key": os.environ["REVID_API_KEY"], "Content-Type": "application/json"}


def build_payload(script: dict, webhook_url: str | None = None) -> dict:
    """Map a generated script onto Revid's render request."""
    payload = dict(config.REVID_DEFAULTS)
    payload.update({
        # The narration the AI voice will read:
        "inputText": script["narration"],
        # Per-scene visual prompts (one image/clip per beat):
        "visualPrompts": script.get("scene_prompts", []),
        "title": script.get("youtube_title", script["title"]),
    })
    if webhook_url:
        payload["webhookUrl"] = webhook_url
    return payload


def create_video(script: dict, webhook_url: str | None = None) -> dict:
    """Kick off a render. Returns Revid's JSON response (includes a project id)."""
    payload = build_payload(script, webhook_url)
    r = requests.post(config.REVID_CREATE_ENDPOINT, json=payload, headers=_headers(), timeout=60)
    r.raise_for_status()
    data = r.json()
    print(f"[revid] render started: {data}")
    return data


def poll_status(pid: str, interval=30, timeout=900) -> dict:
    """Poll until the render is done (up to ~15 min). Returns final status JSON."""
    waited = 0
    while waited < timeout:
        r = requests.get(f"{config.REVID_STATUS_ENDPOINT}/{pid}", headers=_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        state = str(data.get("status", "")).lower()
        print(f"[revid] {pid} status={state} ({waited}s)")
        if state in ("ready", "done", "completed", "success"):
            return data
        if state in ("error", "failed"):
            raise RuntimeError(f"Revid render failed: {data}")
        time.sleep(interval)
        waited += interval
    raise TimeoutError(f"Render {pid} not finished after {timeout}s")
