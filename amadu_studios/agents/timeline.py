"""
Amadu Studios — Dialogue Timeline
===================================
Spec step 2: "Before any video generation, create a timeline.
Every shot knows exactly which dialogue occurs during it."

How it works:
  1. Load all scenes and shots for the episode (ordered).
  2. Load all screenplay lines for the episode.
  3. Assign dialogue lines to shots:
       - Dialogue shots (face shot types) in a scene get the lines spoken
         by characters present in THAT scene, in order.
       - Wide/action/insert shots get no dialogue.
  4. For each assigned dialogue block, find the actual _line_NNN.mp3 files
     on disk and concatenate them into a per-shot audio file.
  5. Measure the audio duration with ffprobe — this becomes the shot's
     duration_sec. The video model renders exactly that many seconds.
  6. Return a full timeline dict keyed by shot_id.

Timeline entry format:
  {
    "shot_id":      int,
    "shot_class":   "dialogue" | "action" | "establishing" | "ambient",
    "speaker":      "Sarah" | "" (empty for silent shots),
    "lines":        ["I think someone is here.", ...],
    "audio_path":   "/path/to/shot_42_audio.mp3" | "",
    "duration_sec": 2.14,   # from audio for dialogue, default for silent
  }
"""
from __future__ import annotations
import os, json, subprocess, shutil
from amadu_studios.database import db
from amadu_studios.agents import shot_classifier


# ── Audio helpers ──────────────────────────────────────────────────────────────

def _audio_duration(path: str) -> float:
    """Measure audio file duration in seconds using ffprobe."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", path],
            stderr=subprocess.DEVNULL)
        return round(float(out.strip()), 3)
    except Exception:
        return 0.0


def _concat_audio(parts: list[str], dest: str) -> bool:
    """Concatenate audio files into dest. Returns True on success."""
    if not parts:
        return False
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if len(parts) == 1:
        shutil.copy(parts[0], dest)
        return True
    concat_txt = dest + "_concat.txt"
    with open(concat_txt, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", concat_txt,
             "-c", "copy", dest],
            check=True)
        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        try:
            os.remove(concat_txt)
        except OSError:
            pass


# ── Line-to-shot assignment ────────────────────────────────────────────────────

def _assign_lines_to_shots(shots: list[dict], scene: dict,
                            screenplay_lines: list[dict],
                            char_map: dict) -> dict:
    """
    Distribute the screenplay lines for THIS SCENE across the face shots in it.

    Strategy:
      - Find which characters are in the scene.
      - Filter screenplay lines to lines spoken by those characters.
      - Identify face shots in the scene (in shot order).
      - Assign lines round-robin to face shots in order.
        (Shot 2 = line 1, Shot 4 = line 2, Shot 2 again = line 3, etc.)
      - Wide/insert shots remain silent.

    Returns: {shot_id: [line_dict, ...]}
    """
    char_ids = json.loads(scene.get("characters_json", "[]"))
    char_names_upper = {
        char_map[cid]["name"].upper()
        for cid in char_ids if cid in char_map
    }
    # Also accept first-name matches
    first_names = {name.split()[0] for name in char_names_upper}

    # Scene's dialogue lines (spoken by scene characters, not Narrator)
    scene_lines = []
    for line in screenplay_lines:
        spk = line.get("speaker", "").upper().strip()
        if spk in ("NARRATOR", "NARRATION", ""):
            continue
        spk_first = spk.split()[0]
        if spk in char_names_upper or spk_first in first_names:
            scene_lines.append(line)

    if not scene_lines:
        return {}

    # Face shots in this scene (ordered)
    face_shots = [s for s in shots
                  if s["shot_type"] in shot_classifier.FACE_SHOT_TYPES]
    if not face_shots:
        return {}

    # Assign lines round-robin across face shots
    assignment: dict[int, list] = {s["id"]: [] for s in face_shots}
    for i, line in enumerate(scene_lines):
        target = face_shots[i % len(face_shots)]
        assignment[target["id"]].append(line)

    # Remove empty entries
    return {sid: lines for sid, lines in assignment.items() if lines}


# ── Main public API ────────────────────────────────────────────────────────────

def build_timeline(ep_id: int, out_dir: str,
                   prod_id: int = None) -> dict[int, dict]:
    """
    Build the complete shot-to-dialogue timeline for an episode.

    Called AFTER voice generation (so _line_NNN.mp3 files exist).
    Called BEFORE video rendering (so renderers know durations).

    Returns: {shot_id: timeline_entry_dict}
    """
    # Load all scenes + shots
    scenes = db.get_scenes(ep_id)
    screenplay_lines = db.get_screenplay(ep_id)

    # Build character name map
    char_map: dict[int, dict] = {}
    if prod_id:
        for c in db.get_characters(prod_id):
            char_map[c["id"]] = c

    timeline: dict[int, dict] = {}

    for scene_idx, scene in enumerate(scenes):
        shots = db.get_shots(scene["id"])
        if not shots:
            continue

        # Assign dialogue lines to face shots in this scene
        assignments = _assign_lines_to_shots(shots, scene, screenplay_lines, char_map)

        for shot_idx, shot in enumerate(shots):
            shot_id   = shot["id"]
            is_first  = (shot_idx == 0)
            has_dlg   = shot_id in assignments and len(assignments[shot_id]) > 0

            # Classify the shot
            cls = shot_classifier.classify(
                shot_type             = shot.get("shot_type", "MS"),
                scene_objective       = scene.get("objective", ""),
                has_dialogue          = has_dlg,
                is_first_shot_of_scene = is_first,
            )

            # Build the audio file for dialogue shots
            audio_path   = ""
            duration_sec = shot_classifier.default_duration(cls)
            speaker      = ""
            lines_text   = []

            if has_dlg:
                assigned_lines = assignments[shot_id]
                speaker = assigned_lines[0].get("speaker", "")
                lines_text = [l.get("text", "") for l in assigned_lines]

                # Collect the _line_NNN.mp3 files for these lines
                mp3_parts = []
                for line in assigned_lines:
                    order = line.get("line_order", -1)
                    lp = os.path.join(out_dir, f"_line_{order:03d}.mp3")
                    if os.path.exists(lp):
                        mp3_parts.append(lp)

                if mp3_parts:
                    audio_dest = os.path.join(out_dir, f"_shot_{shot_id}_audio.mp3")
                    if not os.path.exists(audio_dest):
                        _concat_audio(mp3_parts, audio_dest)
                    if os.path.exists(audio_dest):
                        audio_path   = audio_dest
                        dur          = _audio_duration(audio_dest)
                        # Add 0.3s tail padding so video doesn't cut off the last word
                        duration_sec = max(dur + 0.3, 1.5) if dur > 0 else duration_sec

            entry = {
                "shot_id":      shot_id,
                "shot_class":   cls,
                "speaker":      speaker,
                "lines":        lines_text,
                "audio_path":   audio_path,
                "duration_sec": round(duration_sec, 3),
            }
            timeline[shot_id] = entry

            # Write back to DB so continuity/QA can read it
            db.update_shot(
                shot_id,
                shot_class  = cls,
                audio_path  = audio_path,
                duration_sec = round(duration_sec, 3),
            )

    total = len(timeline)
    dlg   = sum(1 for e in timeline.values() if e["shot_class"] == "dialogue")
    act   = sum(1 for e in timeline.values() if e["shot_class"] == "action")
    est   = sum(1 for e in timeline.values() if e["shot_class"] == "establishing")
    amb   = sum(1 for e in timeline.values() if e["shot_class"] == "ambient")
    print(f"[timeline] {total} shots classified: "
          f"{dlg} dialogue | {act} action | {est} establishing | {amb} ambient")

    return timeline


def print_timeline(timeline: dict[int, dict]):
    """Debug helper — prints the full timeline in readable form."""
    print("\n── DIALOGUE TIMELINE ──────────────────────────────────────")
    for shot_id, entry in sorted(timeline.items()):
        cls  = entry["shot_class"].upper()[:4]
        dur  = f"{entry['duration_sec']:.2f}s"
        spk  = entry["speaker"] or "—"
        text = " | ".join(entry["lines"])[:60] if entry["lines"] else "(silent)"
        print(f"  Shot {shot_id:03d}  [{cls}]  {dur}  {spk}: {text}")
    print("────────────────────────────────────────────────────────────\n")
