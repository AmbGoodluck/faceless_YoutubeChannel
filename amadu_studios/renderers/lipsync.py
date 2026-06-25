"""
Amadu Studios — Lip-Sync Hybrid Renderer
=========================================
Hollywood shot pipeline: every shot class routes to a different video model.

Shot class routing (set by timeline.py + shot_classifier.py):

  dialogue    (MCU/CU/ECU with speaking character)
      → Lip-sync AI: MuseTalk / LatentSync / SadTalker / EchoMimic / Wav2Lip
        Input: portrait image + character audio → talking-head video
        Duration: driven by actual audio length (from timeline)

  action      (motion + movement shots)
      → Image-to-video AI: Wan2.1 / CogVideoX / LTX
        Input: image + motion prompt → animated clip

  establishing (first wide shot of scene)
      → Slow cinematic: LTX-Video / Ken-Burns
        Input: image → gentle push or pan

  ambient     (inserts, silhouettes, environment detail)
      → Ken-Burns zoom (free, FFmpeg)

Lip-sync models (LIPSYNC_MODEL in config.py):
  "musetalk"    — Open-source, fast, good quality. (Recommended)
  "latentsync"  — Sharpest lip movement. bytedance/latentsync on Replicate.
  "sadtalker"   — Established, reliable head movement. cjwbw/sadtalker.
  "echomimic"   — Natural expressions + head pose. jhj0517/echomimic-v2.
  "wav2lip"     — Classic, fastest. man1ky/wav2lip-hd.

Cost (Replicate, June 2026):
  MuseTalk   ~$0.01 per dialogue clip
  LatentSync ~$0.02–0.03 per dialogue clip
  SadTalker  ~$0.01–0.02 per dialogue clip
  Wan2.1     ~$0.03–0.04 per motion clip
  Ken-Burns  Free (FFmpeg)
  Total      ~$0.40–0.70 per 18-shot part
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
    "musetalk":   "lucataco/musetalk",            # fast, open-source, good quality
    "latentsync": "bytedance/latentsync",          # sharpest lips, newer
    "sadtalker":  "cjwbw/sadtalker",               # reliable, natural head movement
    "echomimic":  "jhj0517/echomimic-v2",          # natural expressions + head pose
    "wav2lip":    "man1ky/wav2lip-hd",             # classic, fastest
}

MOTION_MODELS = {
    "wan":      "wavespeed-ai/wan-2.1-i2v-480p",  # best motion coherence
    "cogvideo": "zsxkib/cogvideox-5b",
    "ltx":      "lightricks/ltx-video",            # fastest, good for establishing shots
}
MOTION_MODEL = MOTION_MODELS["wan"]               # default for action shots

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
                     out_dir: str, seconds: float = 5.0) -> str:
        out_path = os.path.join(out_dir, f"shot_{shot_id}.mp4")
        if os.path.exists(out_path):
            return out_path

        # Read shot_class and duration_sec from DB (set by timeline.py)
        shot_class   = "ambient"
        duration_sec = seconds
        audio_path   = ""
        with db.tx() as conn:
            row = conn.execute(
                "SELECT shot_type, shot_class, duration_sec, audio_path FROM shots WHERE id=?",
                (shot_id,)).fetchone()
            if row:
                shot_class   = row["shot_class"]   or "ambient"
                duration_sec = row["duration_sec"] or seconds
                audio_path   = row["audio_path"]   or ""

        # Route by shot class (set by dialogue timeline)
        if shot_class == "dialogue":
            return self._render_lipsync(
                shot_id, image_path, out_dir, out_path,
                seconds=duration_sec, audio_path=audio_path or None)

        elif shot_class in ("action", "establishing"):
            return self._render_motion(
                shot_id, image_path, prompt, out_dir, out_path,
                seconds=duration_sec)

        else:
            # ambient / insert — Ken-Burns (free)
            return super().render_video(shot_id, image_path, prompt, out_dir,
                                        seconds=int(max(2, duration_sec)))

    # ── Lip-sync path ─────────────────────────────────────────────────────────

    def _render_lipsync(self, shot_id: int, image_path: str,
                        out_dir: str, out_path: str,
                        seconds: float = 4.0, audio_path: str = None) -> str:
        token = self._get_token()

        # Use pre-resolved audio from timeline, fall back to legacy extraction
        if not audio_path or not os.path.exists(audio_path):
            audio_path = _get_character_audio(shot_id, out_dir)

        if not audio_path:
            print(f"[lipsync] shot {shot_id}: no character audio, falling back to motion")
            return self._render_motion(shot_id, image_path, "", out_dir, out_path, seconds)

        model_id = LIPSYNC_MODELS[self.lipsync_model_key]
        print(f"[lipsync] shot {shot_id} ({self.lipsync_model_key}) "
              f"lip-sync {seconds:.2f}s ...")

        try:
            if self.lipsync_model_key == "musetalk":
                video_url = self._run_musetalk(token, model_id, image_path, audio_path)
            elif self.lipsync_model_key == "latentsync":
                video_url = self._run_latentsync(token, model_id, image_path, audio_path)
            elif self.lipsync_model_key == "sadtalker":
                video_url = self._run_sadtalker(token, model_id, image_path, audio_path)
            elif self.lipsync_model_key == "echomimic":
                video_url = self._run_echomimic(token, model_id, image_path, audio_path)
            else:
                # wav2lip and unknown
                video_url = self._run_wav2lip(token, model_id, image_path, audio_path)
        except Exception as e:
            print(f"[lipsync] shot {shot_id} lip-sync failed ({e}), falling back to motion")
            return self._render_motion(shot_id, image_path, "", out_dir, out_path, seconds)

        _download(video_url, out_path)
        db.update_shot(shot_id, video_path=out_path, render_status="video_done")
        db.log_render(shot_id, f"{self.name}/{self.lipsync_model_key}", 1, "success", out_path)
        print(f"[lipsync] shot {shot_id} lip-sync -> {out_path}")
        return out_path

    def _run_musetalk(self, token: str, model_id: str,
                      image_path: str, audio_path: str) -> str:
        """MuseTalk — fast, open-source, good quality. lucataco/musetalk on Replicate."""
        return _replicate_run(token, model_id, {
            "face_image": _b64(image_path, "image/jpeg"),
            "audio":      _b64(audio_path, "audio/mpeg"),
            "bbox_shift": 0,       # 0 = natural mouth region
            "fps":        25,
        }, timeout_min=8)

    def _run_echomimic(self, token: str, model_id: str,
                       image_path: str, audio_path: str) -> str:
        """EchoMimic v2 — natural expressions + head pose. jhj0517/echomimic-v2."""
        return _replicate_run(token, model_id, {
            "ref_image":  _b64(image_path, "image/jpeg"),
            "audio":      _b64(audio_path, "audio/mpeg"),
            "width":      512,
            "height":     512,
            "steps":      20,
            "cfg":        2.5,
        }, timeout_min=12)

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
                       out_dir: str, out_path: str, seconds: float = 4.0) -> str:
        """Wan2.1 image-to-video for action and establishing shots."""
        token  = self._get_token()
        motion = getattr(config, "AI_MOTION",
                         "slow cinematic camera push, eerie horror atmosphere")
        full_prompt = f"{motion}. {prompt[:150]}" if prompt else motion

        try:
            video_url = _replicate_run(token, MOTION_MODEL, {
                "image":       _b64(image_path, "image/jpeg"),
                "prompt":      full_prompt,
                "num_frames":  max(33, int(seconds * 16)),
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
