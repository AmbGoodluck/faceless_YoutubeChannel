"""
Amadu Studios — Shot Classifier
================================
Every shot is classified into one of four categories before rendering.
The category determines which video model branch runs.

Four classes:

  dialogue    — Close-up with a speaking character.
                Model: lip-sync AI (MuseTalk / LatentSync / SadTalker / EchoMimic).
                Input: image + character audio → talking-head video.
                The lip animation is driven by the actual voice audio.

  action      — Character is moving, fighting, running, opening doors etc.
                Model: image-to-video motion AI (Wan2.1 / CogVideoX / LTX).
                Input: image + motion prompt → animated clip.

  establishing — First wide shot of a new location. Sets the scene.
                Model: slow cinematic camera (LTX / SVD / Ken-Burns).
                Input: image → gentle push or pan.

  ambient     — Environmental detail, inserts, silhouettes, reflections.
                Model: Ken-Burns or subtle motion AI.
                Input: image → very slow zoom or still with grain.

Classification logic (in priority order):
  1. If shot has assigned dialogue AND shot_type is a face shot → dialogue
  2. If scene objective contains action keywords → action
  3. If shot_type is ES/WS/MWS/BIRD and it's the first shot of the scene → establishing
  4. Everything else → ambient
"""
from __future__ import annotations

# ── Shot type sets ─────────────────────────────────────────────────────────────

FACE_SHOT_TYPES = {
    "MCU", "CU", "ECU",   # close-ups — face fills frame
    "RXN",                 # reaction shot
    "OTS",                 # over-the-shoulder — face visible
    "TWO",                 # two-shot — both faces
    "MS",                  # medium shot — face readable
}

WIDE_SHOT_TYPES = {
    "ES",   # establishing
    "WS",   # wide
    "MWS",  # medium wide
    "BIRD", # bird's eye
    "HIGH", # high angle
}

ACTION_SHOT_TYPES = {
    "LOW",    # low angle — power/threat
    "DUTCH",  # dutch tilt — unease
    "POV",    # point-of-view — immersive
    "CRANE",  # sweeping crane
    "TRACK",  # lateral tracking
}

INSERT_SHOT_TYPES = {
    "INS",  # close on object
    "SIL",  # silhouette
    "REFL", # reflection
    "RACK", # rack focus
    "GRP",  # group
}

# ── Action keyword detection ───────────────────────────────────────────────────

ACTION_KEYWORDS = {
    "running", "chasing", "chase", "fighting", "fight", "attack", "attacked",
    "escaping", "escape", "flee", "flees", "climbing", "jumping", "falling",
    "walking", "stumbles", "crawls", "scrambles", "drags", "throws", "slams",
    "opening", "opens", "closes", "turns", "spins", "reaches", "grabs",
    "pointing", "searching", "rushing", "sprinting", "staggers",
}


# ── Main classifier ────────────────────────────────────────────────────────────

def classify(shot_type: str,
             scene_objective: str,
             has_dialogue: bool,
             is_first_shot_of_scene: bool = False) -> str:
    """
    Classify a shot into one of four production classes.

    Args:
        shot_type:             e.g. "MCU", "ES", "WS"
        scene_objective:       the director's objective for this scene
        has_dialogue:          True if this shot has assigned speaking lines
        is_first_shot_of_scene: True if shot_num == 1 in the scene

    Returns:
        One of: "dialogue" | "action" | "establishing" | "ambient"
    """
    # Priority 1 — Speaking character in a face shot → lip sync
    if has_dialogue and shot_type in FACE_SHOT_TYPES:
        return "dialogue"

    # Priority 2 — Action keywords in objective → motion video
    obj_lower = scene_objective.lower() if scene_objective else ""
    if any(kw in obj_lower for kw in ACTION_KEYWORDS):
        # Wide shots during action scenes are still establishing/ambient
        # Only face/action shot types go to action renderer
        if shot_type not in WIDE_SHOT_TYPES:
            return "action"

    # Priority 3 — First wide shot of the scene → establishing
    if shot_type in WIDE_SHOT_TYPES and is_first_shot_of_scene:
        return "establishing"

    # Priority 4 — Wide shots later in scene → ambient (environment)
    if shot_type in WIDE_SHOT_TYPES:
        return "ambient"

    # Priority 5 — Insert/detail shots → ambient
    if shot_type in INSERT_SHOT_TYPES:
        return "ambient"

    # Default — everything else gets ambient treatment
    return "ambient"


def default_duration(shot_class: str) -> float:
    """
    Default clip duration in seconds when no audio drives the length.
    Dialogue shots are driven by audio length — this is only the fallback.
    """
    return {
        "dialogue":    4.0,   # overridden by actual audio length
        "action":      4.0,   # punchy action cuts
        "establishing": 5.0,  # linger on the location
        "ambient":     3.0,   # insert shots are brief
    }.get(shot_class, 4.0)
