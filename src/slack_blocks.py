"""
Slack messages WITH interactive Approve/Reject buttons (posted via webhook).
Button clicks are sent by Slack to your Cloudflare Worker, which triggers the next
GitHub Actions stage. The button 'value' carries "<action>:<episode>".
"""
import os, requests


def _post(blocks, text="Lights Out Tales"):
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        print("[slack] no webhook set"); return
    try:
        requests.post(url, json={"text": text, "blocks": blocks}, timeout=20).raise_for_status()
        print("[slack] sent")
    except Exception as e:
        print(f"[slack] failed (non-fatal): {e}")


def _approve_block(action: str, episode: str, label: str):
    return {
        "type": "actions",
        "elements": [
            {"type": "button", "style": "primary",
             "text": {"type": "plain_text", "text": label},
             "action_id": "approve", "value": f"{action}:{episode}"},
            {"type": "button", "style": "danger",
             "text": {"type": "plain_text", "text": "Skip"},
             "action_id": "reject", "value": f"skip:{episode}"},
        ],
    }


def script_for_approval(episode: str, data: dict):
    _post([
        {"type": "header", "text": {"type": "plain_text",
            "text": f"Script: {data.get('title','')}"[:150]}},
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f"```{data.get('narration','')[:2800]}```"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": "Approve to render the video."}]},
        _approve_block("render", episode, "✅ Approve → render"),
    ], text=f"New script ready: {data.get('title','')}")


def video_for_approval(episode: str, title: str, watch_link: str):
    _post([
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f":clapper: *Video ready — {title}*\n<{watch_link}|▶︎ Watch on Google Drive>"}},
        _approve_block("publish", episode, "✅ Approve → publish"),
    ], text=f"Video ready: {title}")


def published(title: str, youtube_link: str, clips: list):
    lines = [f":rocket: *Published — {title}*", f"YouTube: {youtube_link}", "",
             "*TikTok clips — download from Drive, paste each caption:*"]
    _post([{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]
          + [{"type": "section", "text": {"type": "mrkdwn",
              "text": f"*Part {c['part']}* — <{c['link']}|download>\n```{c['caption']}```"}}
             for c in clips],
          text=f"Published: {title}")
