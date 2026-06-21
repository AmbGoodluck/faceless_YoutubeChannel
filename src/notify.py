"""
Slack notifications via a free Incoming Webhook.
Set SLACK_WEBHOOK_URL in .env. If it's unset, these calls do nothing (no crash),
so the pipeline still works without Slack.

Create the webhook: https://api.slack.com/messaging/webhooks
  -> Create app -> Incoming Webhooks -> add to a channel -> copy the URL.
"""
from __future__ import annotations
import os, json, requests


def _post(text: str, blocks=None):
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        print("[slack] no SLACK_WEBHOOK_URL set — skipping notification")
        return
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        requests.post(url, json=payload, timeout=20).raise_for_status()
        print("[slack] sent")
    except Exception as e:
        print(f"[slack] failed (non-fatal): {e}")


def script_ready(rid: str, data: dict):
    narration = data.get("narration", "")
    title = data.get("youtube_title", data.get("title", ""))
    _post(
        f":scroll: *New script ready — episode {rid}*\n*{title}*",
        blocks=[
            {"type": "header", "text": {"type": "plain_text", "text": f"Script {rid}: {data.get('title','')}"[:150]}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"```{narration[:2800]}```"}},
            {"type": "context", "elements": [{"type": "mrkdwn",
                "text": (f"Edit `outputs/.../narration.txt` if you want changes, then build the video:  "
                         f"`python src/run_pipeline.py --render {rid}`")}]},
        ],
    )


def video_ready(rid: str, path: str, watch_link: str | None = None):
    link = f"\n:eye: Watch (unlisted): {watch_link}" if watch_link else ""
    _post(
        f":clapper: *Video ready — episode {rid}*\nLocal file: `{path}`{link}\n"
        f"Approve & publish everywhere:  `python src/run_pipeline.py --publish {rid}`")


def published(rid: str, youtube_id: str | None, clip_dir: str):
    yt = f"\n:white_check_mark: YouTube: https://youtu.be/{youtube_id}" if youtube_id else ""
    _post(
        f":rocket: *Published — episode {rid}*{yt}\n"
        f"3 TikTok/Shorts clips ready in `{clip_dir}` — queue them in Metricool "
        f"for 08:00 / 13:00 / 19:00.")
