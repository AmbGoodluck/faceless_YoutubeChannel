"""
Amadu Studios — Lip-Sync Hybrid Renderer
=========================================
The most realistic output for a talking-character horror channel.

How it works per shot:
  Dialogue shots (CU, MCU, OTS, RXN, TWO)
      → SadTalker or LatentSync on Replicate
        Character portrait + character's audio lines → talking-head video
        Characters actually move their mouths in sync with the voice.

  Wide / environment shots (ES, WS, MWS, LOW, HIGH, BIRD, DUTCH)
      → Wan2.1 image-to-video on Replicate
        Adds real environmental motion: wind, shadows, camera push.

  Insert / no-face shots (INS, SIL, REFL)
      → Ken-Burns zoom (free, FFmpeg)
        No face present so lip sync isn't needed.

Cost (Replicate, June 2026):
  SadTalker  ~$0.01–0.02 per dialogue clip
  LatentSync ~$0.02–0.03 per dialogue clip  (higher quality)
  Wan2.1     ~$0.03–0.04 per wide clip
  Total      ~$0.40–0.70 per 16-shot part

Setup (one API token covers everything):
  1. Create account at replicate.com
  2. replicate.com/account/api-tokens → Create Token
  3. pip install replicate --break-system-packages
  4. Add to .env:   REPLICATE_API_TOKEN=r8_xxxxxxxxxx
  5. In config.py:  VIDEO_MODE = "lipsync"
     OR per-run:    VIDEO_PROVIDER=lipsync python amadu_studios/run.py --part 1

Model selection (LIPSYNC_MODEL in config.py):
  "sadtalker"   — Established, reliable. cjwbw/sadtalker on Replicate.
  "latentsync"  — Newer, sharper lip movements. bytedance/latentsync.
  "wav2lip"     — Classic, fastest. Slightly lower quality. man1ky/wav2lip-hd.
"""
from __future__ import annotations
import os, time, base64, subprocess, json
import requests

from amadu_studios.renderers.pollinations import PollinationsRenderer
from amadu_studios.database import db
import config

# ── Shot routing ──────────────────────────────────────────────────────────────

# These shot types show character faces → use lip sync
DIALOGUE_SHOT_TYPES = {"MCU", "CU", "ECU", "OTS", "TWO", "RXN", "MS"}

# These shot types show wide environment → use motion video
MOTION_SHOT_TYPES   = {"ES", "WS", "MWS", "LOW", "HIGH", "BIRD", "DUTCH", "POV", "CRANE"}

# These have no face → Ken-Burns is fine
INSERT_SHOT_TYPES   = {"INS", "SIL", "REFL", "RACK", "GRP"}

# ── Replicate model IDs ───────────────────────────────────────────────────────

LIPSYNC_MODELS = {
    "sadtalker":  "cjwbw/sadtalker",
    "latentsync": "bytedance/latentsync",
    "wav2lip":    "man1ky/wav2lip-hd",
}

MOTION_MODEL = "wavespeed-ai/wan-2.1-i2v-480p"   # same as replicate.py

REPLICATE_API = "https://api.replicate.com/v1"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _b64(path: str, mime: str = "image/jpeg") -> str:
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def _replicate_run(token: str, model: str, inputs: dict, timeout_min: int = 15) -> str:
    """
    Submit a Replicate prediction and poll until done.
    Returns the output URL (video or audio).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Prefer":        "wait",
    }

    r = requests.post(
        f"{REPLICATE_API}/models/{model}/predictions",
        headers=headers,
        json={"input": inputs},
        timeout=30)
    if r.status_code == 422:
        raise RuntimeError(f"Replicate 422 (bad input) for {model}: {r.text[:400]}")
    if r.status_code == 401:
        raise RuntimeError("REPLICATE_API_TOKEN invalid — check replicate.com/account")
    r.raise_for_status()

    pred     = r.json()
    pred_id  = pred.get("id")
    if not pred_id:
        raise RuntimeError(f"Replicate returned no prediction id: {pred}")

    # Poll
    poll_url = f"{REPLICATE_API}/predictions/{pred_id}"
    for _ in range(timeout_min * 6):   # poll every 10s
        time.sleep(10)
        resp = requests.get(poll_url, headers=headers, timeout=30).json()
        status = resp.get("status", "")
        if status == "succeeded":
            out = resp.get("output")
            if isinstance(out, list):
                return out[0]
            return out
        if status in ("failed", "canceled"):
            raise RuntimeError(f"Replicate {model} {status}: {resp.get('error', '')}")

    raise TimeoutError(f"Replicate {model} timed out after {timeout_min} min")


def _download(url: str, dest: str):
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "wb") as f:
        f.write(r.content)


# ── Audio extraction ──────────────────────────────────────────────────────────

def _get_character_audio(shot_id: int, out_dir: str) -> str | None:
    """
    Find the audio for the primary speaking character in this shot's scene.

    Strategy:
      1. Look up shot → scene → episode
      2. Find screenplay lines for this episode spoken by characters in the scene
      3. Collect matching _line_NNN.mp3 files (kept by _generate_voice)
      4. Concatenate into a per-character audio file for this scene
      5. Return the path, or None if no dialogue lines found

    Edge TTS generates individual _line_NNN.mp3 files (one per screenplay line).
    These are preserved on disk so we can use them here.
    """
    # Get shot → scene → episode chain
    shot = None
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM shots WHERE id=?", (shot_id,)).fetchone()
        if row:
            shot = dict(row)
    if not shot:
        return None

    scene = None
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM scenes WHERE id=?", (shot["scene_id"],)).fetchone()
        if row:
            scene = dict(row)
    if not scene:
        return None

    char_ids = json.loads(scene.get("characters_json", "[]"))
    if not char_ids:
        return None

    # Get episode and characters
    ep_id = scene["episode_id"]
    chars = [db.get_character(cid) for cid in char_ids if cid]
    char_names_upper = {c["name"].upper() for c in chars if c}

    # Get all screenplay lines for this episode
    all_lines = db.get_screenplay(ep_id)

    # Find lines spoken by characters in this scene
    matching_orders = []
    for line in all_lines:
        spk = line.get("speaker", "").upper().strip()
        # Match full name or first name
        matched = any(
            spk == name or spk == name.split()[0]
            for name in char_names_upper
            if spk not in ("NARRATOR", "NARRATION", "")
        )
        if matched:
            matching_orders.append(line["line_order"])

    if not matching_orders:
        return None

    # Collect _line_NNN.mp3 files for matching orders
    audio_parts = []
    for order in matching_orders:
        line_path = os.path.join(out_dir, f"_line_{order:03d}.mp3")
        if os.path.exists(line_path):
            audio_parts.append(line_path)

    if not audio_parts:
        return None

    # Concatenate into one character audio file for this shot
    char_audio_path = os.path.join(out_dir, f"_char_audio_shot_{shot_id}.mp3")
    if os.path.exists(char_audio_path):
        return char_audio_path

    if len(audio_parts) == 1:
        import shutil
        shutil.copy(audio_parts[0], char_audio_path)
    else:
        concat_txt = os.path.join(out_dir, f"_char_concat_{shot_id}.txt")
        with open(concat_txt, "w") as f:
            for p in audio_parts:
                f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", concat_txt,
             "-c", "copy", char_audio_path],
            check=True)
        try:
            os.remove(concat_txt)
        except OSError:
            pass

    return char_audio_path


# ── Main renderer ─────────────────────────────────────────────────────────────

class LipSyncRenderer(PollinationsRenderer):
    """
    Hybrid renderer: lip-sync for dialogue shots, motion for wide shots,
    Ken-Burns for inserts. All powered by Replicate + Pollinations.
    """
    name = "lipsync"

    def __init__(self, lipsync_model: str = None):
        self.lipsync_model_key = (
            lipsync_model
            or os.environ.get("LIPSYNC_MODEL")
            or getattr(config, "LIPSYNC_MODEL", "sadtalker")
        )
        if self.lipsync_model_key not in LIPSYNC_MODELS:
            print(f"[lipsync] unknown model '{self.lipsync_model_key}', using sadtalker")
            self.lipsync_model_key = "sadtalker"

    @property
    def supports_video(self) -> bool:
        return True

    def _get_token(self) -> str:
        tok = os.environ.get("REPLICATE_API_TOKEN", "")
        if not tok:
            raise RuntimeError(
                "REPLICATE_API_TOKEN not set.\n"
                "  1. Sign up at replicate.com\n"
                "  2. replicate.com/account/api-tokens → Create Token\n"
                "  3. Add REPLICATE_API_TOKEN=r8_xxxxx to .env"
            )
        return tok

    def render_video(self, shot_id: int, image_path: str, prompt: str,
                     out_dir: str, seconds: int = 5) -> str:
        out_path = os.path.join(out_dir, f"shot_{shot_id}.mp4")
        if os.path.exists(out_path):
            return out_path

        # Determine shot type from DB
        shot_type = "MS"
        with db.tx() as conn:
            row = conn.execute("SELECT shot_type FROM shots WHERE id=?", (shot_id,)).fetchone()
            if row:
                shot_type = row["shot_type"] or "MS"

        # Route to the right renderer
        if shot_type in DIALOGUE_SHOT_TYPES:
            return self._render_lipsync(shot_id, image_path, out_dir, out_path, seconds)
        elif shot_type in MOTION_SHOT_TYPES:
            return self._render_motion(shot_id, image_path, prompt, out_dir, out_path, seconds)
        else:
            # Inserts and unknown — Ken-Burns
            return super().render_video(shot_id, image_path, prompt, out_dir, seconds)

    # ── Lip-sync path ─────────────────────────────────────────────────────────

    def _render_lipsync(self, shot_id: int, image_path: str,
                        out_dir: str, out_path: str, seconds: int) -> str:
        token      = self._get_token()
        audio_path = _get_character_audio(shot_id, out_dir)

        if not audio_path:
            # No dialogue lines for this character — fall back to motion video
            print(f"[lipsync] shot {shot_id}: no character audio, falling back to motion")
            return self._render_motion(shot_id, image_path, "", out_dir, out_path, seconds)

        model_id = LIPSYNC_MODELS[self.lipsync_model_key]
        print(f"[lipsync] shot {shot_id} ({self.lipsync_model_key}) lip-sync...")

        try:
            if self.lipsync_model_key == "sadtalker":
                video_url = self._run_sadtalker(token, model_id, image_path, audio_path)
            elif self.lipsync_model_key == "latentsync":
                video_url = self._run_latentsync(token, model_id, image_path, audio_path)
            else:
                # wav2lip and others
                video_url = self._run_wav2lip(token, model_id, image_path, audio_path)
        except Exception as e:
            print(f"[lipsync] shot {shot_id} lip-sync failed ({e}), falling back to motion")
            return self._render_motion(shot_id, image_path, "", out_dir, out_path, seconds)

        _download(video_url, out_path)
        db.update_shot(shot_id, video_path=out_path, render_status="video_done")
        db.log_render(shot_id, f"{self.name}/{self.lipsync_model_key}", 1, "success", out_path)
        print(f"[lipsync] shot {shot_id} lip-sync -> {out_path}")
        return out_path

    def _run_sadtalker(self, token: str, model_id: str,
                       image_path: str, audio_path: str) -> str:
        return _replicate_run(token, model_id, {
            "source_image":   _b64(image_path, "image/jpeg"),
            "driven_audio":   _b64(audio_path, "audio/mpeg"),
            "enhancer":       "gfpgan",        # face enhancement — sharper output
            "preprocess":     "full",          # don't crop — preserve full frame
            "still":          False,           # allow head movement
            "use_ref_video":  False,
            "pose_style":     0,
            "batch_size":     2,
            "size":           256,
        }, timeout_min=10)

    def _run_latentsync(self, token: str, model_id: str,
                        image_path: str, audio_path: str) -> str:
        return _replicate_run(token, model_id, {
            "video":          _b64(image_path, "image/jpeg"),  # accepts image as source
            "audio":          _b64(audio_path, "audio/mpeg"),
            "guidance_scale": 2.0,
            "inference_steps": 20,
        }, timeout_min=12)

    def _run_wav2lip(self, token: str, model_id: str,
                     image_path: str, audio_path: str) -> str:
        return _replicate_run(token, model_id, {
            "face":           _b64(image_path, "image/jpeg"),
            "audio":          _b64(audio_path, "audio/mpeg"),
            "pads":           "0 10 0 0",
            "smooth":         True,
            "resize_factor":  1,
        }, timeout_min=8)

    # ── Motion path ───────────────────────────────────────────────────────────

    def _render_motion(self, shot_id: int, image_path: str, prompt: str,
                       out_dir: str, out_path: str, seconds: int) -> str:
        """Wan2.1 image-to-video for wide/environment shots."""
        token  = self._get_token()
        motion = getattr(config, "AI_MOTION",
                         "slow cinematic camera push, eerie horror atmosphere")
        full_prompt = f"{motion}. {prompt[:150]}" if prompt else motion

        try:
            video_url = _replicate_run(token, MOTION_MODEL, {
                "image":       _b64(image_path, "image/jpeg"),
                "prompt":      full_prompt,
                "num_frames":  max(33, seconds * 16),
                "sample_steps": 20,
                "fps":         16,
            }, timeout_min=12)
            _download(video_url, out_path)
            db.update_shot(shot_id, video_path=out_path, render_status="video_done")
            db.log_render(shot_id, f"{self.name}/wan2.1", 1, "success", out_path)
            print(f"[lipsync] shot {shot_id} motion (Wan2.1) -> {out_path}")
            return out_path
        except Exception as e:
            print(f"[lipsync] shot {shot_id} Wan2.1 failed ({e}), falling back to Ken-Burns")
            return super().render_video(shot_id, image_path, prompt, out_dir, seconds)
