"""
Retroactively set the custom thumbnail on already-uploaded episodes.

Use this AFTER verifying the channel at https://www.youtube.com/verify (custom
thumbnails require a verified channel). It walks outputs/<slug>/state.json, and for
every episode that has a saved YouTube id + a thumbnail.jpg, sets the thumbnail.

    python src/set_thumbnails.py            # all episodes that have a saved id
    python src/set_thumbnails.py <videoId> <path/to/thumbnail.jpg>   # one specific video
"""
import os, sys, json, glob
import googleapiclient.http

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import upload_youtube


def _set(yt, video_id, thumb):
    yt.thumbnails().set(
        videoId=video_id,
        media_body=googleapiclient.http.MediaFileUpload(thumb)).execute()
    print(f"[thumb] set {video_id} <- {thumb}")


def main():
    yt = upload_youtube._service()
    if len(sys.argv) == 3:
        _set(yt, sys.argv[1], sys.argv[2])
        return
    done = 0
    for state in sorted(glob.glob(os.path.join(config.OUTPUT_DIR, "*", "state.json"))):
        out = os.path.dirname(state)
        st = json.load(open(state))
        vid = st.get("youtube")
        thumb = os.path.join(out, "thumbnail.jpg")
        if not vid:
            print(f"[thumb] skip {os.path.basename(out)} (no saved youtube id)")
            continue
        if not os.path.exists(thumb):
            print(f"[thumb] skip {os.path.basename(out)} (no thumbnail.jpg)")
            continue
        try:
            _set(yt, vid, thumb); done += 1
        except Exception as e:
            print(f"[thumb] FAILED {vid}: {e}")
    print(f"[thumb] done — {done} thumbnail(s) set")


if __name__ == "__main__":
    main()
