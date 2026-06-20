"""
Daily posting reminder. Run this at each posting time (7am / 12pm / 4pm).
It takes the NEXT unposted clip from to_post/queue.json and:
  - opens the video file
  - copies the caption + hashtags to your clipboard (paste straight into the app)
  - shows a macOS notification
  - pings Slack (if SLACK_WEBHOOK_URL is set)
  - marks it posted so the next run serves the next clip

So at each time you just: switch to TikTok/YouTube, paste, attach the open video, post.
"""
import os, sys, json, subprocess

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import package_post
try:
    from src import notify
except Exception:
    notify = None


def _clipboard(text: str):
    try:
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)  # macOS
        p.communicate(text.encode())
    except FileNotFoundError:
        pass


def _macos_notify(title: str, msg: str):
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{msg}" with title "{title}"'])
    except Exception:
        pass


def main():
    queue = package_post._load_queue()
    nxt = next((c for c in queue if not c["posted"]), None)
    if not nxt:
        print("[serve] nothing left to post — queue empty.")
        if notify: notify._post(":hourglass: Posting queue empty — render the next episode.")
        return
    # open the video
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    try: subprocess.run([opener, nxt["file"]])
    except Exception as e: print(f"[serve] could not open video: {e}")
    _clipboard(nxt["caption"])
    title = f"Post now: {nxt['episode']} {nxt['label']}"
    _macos_notify("Lights Out Tales", title + " — caption copied to clipboard")
    if notify:
        notify._post(f":bell: *{title}*\nCaption is on your clipboard. Video opened: `{nxt['file']}`\n```{nxt['caption']}```")
    nxt["posted"] = True
    package_post._save_queue(queue)
    print(f"[serve] served {nxt['episode']} {nxt['label']} — caption copied, video opened.")


if __name__ == "__main__":
    main()
