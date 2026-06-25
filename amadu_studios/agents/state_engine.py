"""
Amadu Studios — Character State Engine
=======================================
Spec requirement: "The state engine updates after every scene and becomes
the input for the next one."

How it works:
  After each scene's shots finish rendering, call update_scene_states().
  It reads the scene's objective + emotional arc, infers state changes
  using keyword matching, and writes to the character_states DB table.

  The cinematographer already reads from character_states (via get_states_for_scene)
  when assembling prompts — so any state written here is automatically injected
  into subsequent shots.

Carrying variables:
  injuries      — accumulates (minor bruising → visible bruising → severe)
  fatigue       — triggered by chase/escape scenes; recovers gradually
  emotional_state — dominant emotion for the scene
  clothing_note — weather-based modifications (rain = soaking wet, etc.)

This is the "carryover" system. Maya's cut from scene 2 appears in scene 5
because the state is written to the DB after scene 2 and read before scene 5.
"""
from __future__ import annotations
import json
from amadu_studios.database import db


# ── Injury inference ──────────────────────────────────────────────────────────

INJURY_KEYWORDS = {
    "attack", "attacked", "fight", "fighting", "struck", "hit", "beaten",
    "stabbed", "cut", "sliced", "wound", "wounded", "bleeding", "blood",
    "grabbed", "thrown", "falls", "crashes", "burns", "burned",
    "slammed", "choked", "clawed", "mauled", "bitten",
}

INJURY_LEVELS = ["", "minor bruising and cuts", "visible bruising and cuts", "severe injuries"]

def _infer_injuries(objective: str, current: str) -> str:
    """
    Escalate injuries if the scene contains violence.
    Injuries accumulate — they don't spontaneously heal.
    """
    text = objective.lower()
    if any(kw in text for kw in INJURY_KEYWORDS):
        try:
            level = INJURY_LEVELS.index(current)
            return INJURY_LEVELS[min(level + 1, len(INJURY_LEVELS) - 1)]
        except ValueError:
            return current or INJURY_LEVELS[1]   # first level if unknown
    return current   # no change — injuries persist until cleared


# ── Fatigue inference ─────────────────────────────────────────────────────────

FATIGUE_KEYWORDS = {
    "running", "chasing", "chase", "escaping", "escape", "flee", "flees",
    "climbing", "struggled", "struggling", "collapses", "barely",
    "sprinting", "crawling", "scrambling", "dragging",
}

FATIGUE_RECOVERY = {
    "visibly winded and exhausted": "visibly tired",
    "visibly tired": "none",
    "none": "none",
}

def _infer_fatigue(objective: str, current: str) -> str:
    text = objective.lower()
    if any(kw in text for kw in FATIGUE_KEYWORDS):
        return "visibly winded and exhausted"
    # Gradual recovery
    return FATIGUE_RECOVERY.get(current, "none")


# ── Emotional state inference ─────────────────────────────────────────────────

EMOTIONAL_MAP = [
    # (keywords, state) — first match wins, most specific first
    ({"kidnapped", "captured", "cornered", "locked in", "trapped", "helpless"}, "terrified"),
    ({"stabbed", "shot", "dying", "bleeding out", "mortally"},                  "dying"),
    ({"death", "killed", "murdered", "dead body", "corpse", "funeral"},         "grieving"),
    ({"realizes", "revelation", "discovers", "truth revealed", "unmasked",
      "figures out", "understands now"},                                          "shocked"),
    ({"argument", "confrontation", "threatening", "accused", "shouts",
      "demands", "screams at"},                                                   "agitated"),
    ({"final", "last chance", "no way out", "only hope", "running out"},         "desperate"),
    ({"decides", "determined", "confronts the", "faces the", "stands her ground",
      "stands his ground"},                                                        "resolved"),
    ({"safe", "escaped", "survived", "made it out", "got away"},                "relieved"),
    ({"investigates", "searches", "looking for", "examines", "explores"},        "cautious"),
    ({"stalked", "hunted", "followed", "being watched", "something wrong"},      "paranoid"),
]

def _infer_emotional_state(objective: str, arc: str) -> str:
    combined = (objective + " " + arc).lower()
    for keywords, state in EMOTIONAL_MAP:
        if any(kw in combined for kw in keywords):
            return state
    return "tense"   # default for a horror scene


# ── Weather clothing note ─────────────────────────────────────────────────────

def _infer_clothing_note(weather: str, current_note: str) -> str:
    """If scene is rainy/snowy, add clothing modification note."""
    w = weather.lower() if weather else ""
    if "rain" in w or "storm" in w:
        return "clothes soaking wet, hair plastered to face"
    if "snow" in w or "blizzard" in w:
        return "shivering, frost on clothing"
    if "fog" in w:
        return current_note   # fog doesn't change clothing
    return current_note   # clear weather — no change


# ── Main public API ───────────────────────────────────────────────────────────

def update_scene_states(ep_id: int, scene_id: int, part_num: int, scene_num: int):
    """
    Called after a scene's shots finish rendering.
    Reads the scene objective + arc, infers state changes,
    writes updated states for all characters in the scene.
    These states are then read by the cinematographer for the NEXT scene.
    """
    scene = None
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM scenes WHERE id=?", (scene_id,)).fetchone()
        if row:
            scene = dict(row)
    if not scene:
        return

    char_ids = json.loads(scene.get("characters_json", "[]"))
    if not char_ids:
        return

    objective = scene.get("objective", "")
    arc       = scene.get("emotional_arc", "")
    weather   = scene.get("weather", "clear")

    new_emotional = _infer_emotional_state(objective, arc)

    for char_id in char_ids:
        # Carry forward from the last recorded state for this character
        prev = db.get_character_state(char_id, part_num, scene_num - 1)

        new_injuries = _infer_injuries(objective, prev.get("injuries", ""))
        new_fatigue  = _infer_fatigue(objective, prev.get("fatigue", "none"))
        new_clothing = _infer_clothing_note(weather, prev.get("clothing_note", ""))

        db.update_character_state(
            char_id       = char_id,
            part_num      = part_num,
            scene_num     = scene_num,
            injuries      = new_injuries,
            fatigue       = new_fatigue,
            emotional_state = new_emotional,
            clothing_note = new_clothing,
        )

    chars_str = ", ".join(str(cid) for cid in char_ids)
    print(f"[state_engine] scene {scene_num} done: updated states for chars [{chars_str}] "
          f"({new_emotional}, injuries='{new_injuries}', fatigue='{new_fatigue}')")


def get_states_for_scene(char_ids: list[int], part_num: int, scene_num: int) -> dict:
    """
    Returns {char_id: state_dict} for all characters in the scene.
    Passed to cinematographer.assemble_prompt() so state is injected into
    every shot prompt for this scene.
    """
    return {cid: db.get_character_state(cid, part_num, scene_num) for cid in char_ids}


def clear_states_on_new_production(prod_id: int):
    """
    Call when starting a new production so old states don't bleed in.
    Not strictly needed (prod_id scoping handles this) but useful for resets.
    """
    # States are indirectly scoped through character_id → character → production_id.
    # No bulk delete needed; get_character_state fetches by char_id which is already
    # production-scoped. This function is a no-op placeholder for future use.
    pass
