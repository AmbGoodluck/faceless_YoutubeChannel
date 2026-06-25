"""
Amadu Studios — Continuity Supervisor
Validates that each shot is consistent with the production's asset registry.

Two tiers of checks:
  Tier 1 — Asset consistency (text/DB checks, zero cost):
    - Image file exists on disk
    - Prompt was assembled from assets (not empty)
    - Shot type is from the recognised library
    - Character names appear in the prompt
    - Colour grade and lighting setup are recorded

  Tier 2 — Vision QA (PIL image checks, zero API cost):
    - Image passes vision_qa.check_image() sanity checks
    - Catches blank frames, corrupt files, wrong dimensions

Runs after every render. Failed shots are flagged in the DB.
The re-render loop in run.py retries failed shots automatically.
Spec: "Continuity Supervisor rejects failed renders automatically."
"""
from __future__ import annotations
import os, json
from amadu_studios.database import db
from amadu_studios.agents import vision_qa as vqa


def check_shot(shot_id: int, prod_id: int, part_num: int) -> bool:
    """
    Run continuity checks for a rendered shot.
    Returns True if all checks pass.
    """
    shot = None
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM shots WHERE id=?", (shot_id,)).fetchone()
        if row:
            shot = dict(row)

    if not shot:
        return False

    checks = {}
    notes = []

    # 1. Image exists on disk
    checks["image_exists"] = bool(shot.get("image_path") and os.path.exists(shot["image_path"]))
    if not checks["image_exists"]:
        notes.append("image_path missing or file not found")

    # 2. Prompt was assembled (not empty)
    checks["prompt_populated"] = bool(shot.get("prompt", "").strip())
    if not checks["prompt_populated"]:
        notes.append("shot prompt is empty")

    # 3. Shot type is a recognised type
    from amadu_studios.agents.cinematographer import SHOT_TYPES
    checks["valid_shot_type"] = shot.get("shot_type", "") in SHOT_TYPES
    if not checks["valid_shot_type"]:
        notes.append(f"unrecognised shot type: {shot.get('shot_type')}")

    # 4. Character references appear in the prompt (basic string check)
    scene = None
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM scenes WHERE id=?", (shot.get("scene_id"),)).fetchone()
        if row:
            scene = dict(row)

    if scene:
        char_ids = json.loads(scene.get("characters_json", "[]"))
        chars = [db.get_character(cid) for cid in char_ids if cid]
        prompt_upper = shot.get("prompt", "").upper()
        all_present = all(
            c["name"].split()[0].upper() in prompt_upper for c in chars if c
        )
        checks["character_refs_in_prompt"] = all_present
        if not all_present:
            missing = [c["name"] for c in chars if c and c["name"].split()[0].upper() not in prompt_upper]
            notes.append(f"character refs missing from prompt: {missing}")

    # 5. Colour grade specified in prompt
    checks["colour_grade_specified"] = bool(shot.get("colour_grade", ""))
    if not checks["colour_grade_specified"]:
        notes.append("no colour grade recorded for this shot")

    # 6. Lighting setup specified
    checks["lighting_specified"] = bool(shot.get("lighting_setup", ""))
    if not checks["lighting_specified"]:
        notes.append("no lighting setup recorded for this shot")

    # 7. Vision QA — PIL image sanity (blank frame, corrupt, wrong dimensions)
    img_path = shot.get("image_path", "")
    if img_path:
        vqa_result = vqa.check_image(shot_id, img_path)
        checks["vision_qa"] = vqa_result["passed"]
        if not vqa_result["passed"]:
            notes.extend(vqa_result["notes"])
    else:
        # No image path yet — skip VQA (will be caught by image_exists check)
        checks["vision_qa"] = checks["image_exists"]

    passed = all(checks.values())
    db.log_continuity(shot_id, checks, passed, "; ".join(notes) if notes else "all clear")

    if passed:
        print(f"[continuity] shot {shot_id} ✓ all checks passed")
    else:
        failed = [k for k, v in checks.items() if not v]
        print(f"[continuity] shot {shot_id} ✗ failed: {failed} — {'; '.join(notes)}")

    return passed


def check_episode(ep_id: int, prod_id: int, part_num: int) -> dict:
    """Run continuity on all shots in an episode. Returns summary."""
    shots = db.get_all_shots_for_episode(ep_id)
    results = {"total": len(shots), "passed": 0, "failed": 0, "failed_ids": []}
    for shot in shots:
        ok = check_shot(shot["id"], prod_id, part_num)
        if ok:
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["failed_ids"].append(shot["id"])
    print(f"[continuity] episode {ep_id}: {results['passed']}/{results['total']} shots passed")
    return results
