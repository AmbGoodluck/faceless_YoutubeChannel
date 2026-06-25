"""
Amadu Studios — Vision QA
==========================
Spec requirement: "Computer vision verifies face embeddings, color histograms,
palette consistency, pose continuity, prop continuity."

What we implement here (pragmatic subset, zero extra cost):
  1. File exists and is not corrupted
  2. File size > minimum threshold (not blank/empty)
  3. Pixel variance check via PIL — detects solid-color / blank frames
  4. Dimensions match target (catches renderer errors)
  5. Reference portrait registration — first CU/MCU of each character becomes
     their canonical anchor (spec's "reference sheets")
  6. Location reference registration — first ES/WS of each location becomes
     the visual anchor for that set

The spec also mentions face embeddings and histogram comparison. Those require
heavier dependencies (face_recognition, scikit-image). They are SAFE to add
later as drop-in upgrades — the VQA result dict is already structured for them.

Renders that fail VQA are flagged in the DB (render_status="vqa_failed") so
the re-render loop in run.py can pick them up.
"""
from __future__ import annotations
import os
from amadu_studios.database import db

# PIL (Pillow) — should already be installed in the pipeline environment
try:
    from PIL import Image, ImageStat
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[vision_qa] WARNING: Pillow not installed. "
          "Install with: pip install Pillow --break-system-packages")

# Shot types where a character face should be the primary subject
FACE_SHOT_TYPES      = {"CU", "MCU", "ECU", "RXN", "OTS", "TWO", "MS"}
# Shot types that establish a location
LOCATION_SHOT_TYPES  = {"ES", "WS", "MWS", "BIRD", "HIGH"}

# Minimum pixel variance for a "non-blank" image (grayscale)
MIN_VARIANCE   = 400
# Minimum file size in bytes (a valid 1920×1080 JPEG should be >> 10KB)
MIN_FILE_BYTES = 8_000


# ── Image sanity checks ────────────────────────────────────────────────────────

def check_image(shot_id: int, image_path: str) -> dict:
    """
    Run sanity checks on a rendered image.

    Returns:
      {
        "passed":  bool,
        "checks":  {"file_exists": bool, "file_size_ok": bool, ...},
        "notes":   ["reason 1", ...]
      }

    On failure, marks shot as render_status="vqa_failed" in DB.
    """
    checks = {}
    notes  = []

    # 1. File exists on disk
    checks["file_exists"] = os.path.exists(image_path) if image_path else False
    if not checks["file_exists"]:
        notes.append(f"image not found at {image_path!r}")
        _flag_failed(shot_id, checks, notes)
        return {"passed": False, "checks": checks, "notes": notes}

    # 2. File size
    size = os.path.getsize(image_path)
    checks["file_size_ok"] = (size >= MIN_FILE_BYTES)
    if not checks["file_size_ok"]:
        notes.append(f"file too small: {size} bytes (min {MIN_FILE_BYTES})")

    if not PIL_AVAILABLE:
        passed = all(checks.values())
        if not passed:
            _flag_failed(shot_id, checks, notes)
        return {"passed": passed, "checks": checks, "notes": notes}

    # 3. PIL checks (open + inspect)
    try:
        img = Image.open(image_path)
        img.verify()
        img = Image.open(image_path)   # re-open after verify() drains the file handle

        # 4. Dimensions
        w, h = img.size
        checks["dimensions_ok"] = (w >= 1280 and h >= 720)
        if not checks["dimensions_ok"]:
            notes.append(f"unexpected dimensions: {w}×{h} (expected ≥1280×720)")

        # 5. Not blank — luminance variance check
        gray  = img.convert("L")
        stat  = ImageStat.Stat(gray)
        var   = stat.var[0]
        checks["not_blank"] = (var >= MIN_VARIANCE)
        if not checks["not_blank"]:
            notes.append(f"image appears blank/solid (luminance variance={var:.0f}, min={MIN_VARIANCE})")

    except Exception as e:
        checks["image_valid"] = False
        notes.append(f"PIL error: {e}")

    passed = all(checks.values())
    if not passed:
        _flag_failed(shot_id, checks, notes)
        print(f"[vision_qa] shot {shot_id} FAILED: {'; '.join(notes)}")
    else:
        print(f"[vision_qa] shot {shot_id} ✓ image ok")

    return {"passed": passed, "checks": checks, "notes": notes}


def _flag_failed(shot_id: int, checks: dict, notes: list):
    db.update_shot(shot_id, render_status="vqa_failed")
    db.log_continuity(shot_id, checks, False, "; ".join(notes))


# ── Reference image registration ───────────────────────────────────────────────

def register_reference_image(shot_id: int, char_ids: list[int], location_id: int,
                              shot_type: str, image_path: str) -> bool:
    """
    Implements the spec's "reference sheets" concept.

    For face shots: register the first good CU/MCU as each character's canonical portrait.
    For location shots: register the first good ES/WS as the location's canonical image.

    These anchors are used to:
      - Keep Pollinations seeds consistent (same seed + same prompt = same face)
      - Provide a visual reference for future renderer upgrades (img2img with Flux/ComfyUI)
      - Verify palette consistency in future VQA upgrades

    Returns True if any registration happened.
    """
    if not os.path.exists(image_path):
        return False

    registered = False

    # Register character reference portraits (face shots only)
    if shot_type in FACE_SHOT_TYPES:
        for char_id in char_ids:
            char = db.get_character(char_id)
            if not char:
                continue
            existing_ref = char.get("reference_image_path", "") or ""
            if not existing_ref or not os.path.exists(existing_ref):
                db.set_character_reference_image(char_id, image_path)
                char_name = char.get("name", f"char_{char_id}")
                print(f"[vision_qa] registered canonical portrait: "
                      f"{char_name} → {os.path.basename(image_path)}")
                registered = True

    # Register location reference image (establishing/wide shots only)
    if shot_type in LOCATION_SHOT_TYPES and location_id:
        with db.tx() as conn:
            row = conn.execute("SELECT reference_image_path FROM locations WHERE id=?",
                               (location_id,)).fetchone()
            if row:
                existing = (row["reference_image_path"] or "")
                if not existing or not os.path.exists(existing):
                    db.set_location_reference_image(location_id, image_path)
                    print(f"[vision_qa] registered location anchor: "
                          f"loc_id={location_id} → {os.path.basename(image_path)}")
                    registered = True

    return registered


# ── Seed resolution ────────────────────────────────────────────────────────────

def resolve_seed(shot_type: str, char_ids: list[int], location_id: int,
                 shot_id: int) -> int:
    """
    Resolve the visual seed for a Pollinations render call.

    Rule:
      Face shots  → primary character's deterministic seed (char_id * 997)
      Wide shots  → location's deterministic seed (loc_id * 7919)
      Other       → original shot_id * 17 (per-shot unique, no consistency guarantee)

    Same seed + same prompt = same Pollinations result.
    Locking face shots to a character seed makes Maya's face more consistent
    across all 18 shots per part and across all 20 parts.
    """
    if shot_type in FACE_SHOT_TYPES and char_ids:
        return db.character_visual_seed(char_ids[0])

    if shot_type in LOCATION_SHOT_TYPES and location_id:
        return db.location_visual_seed(location_id)

    return shot_id * 17   # fallback — per-shot unique seed
