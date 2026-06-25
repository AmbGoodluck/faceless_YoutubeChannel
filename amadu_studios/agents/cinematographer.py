"""
Amadu Studios — Cinematographer Agent
Owns shot type, framing, lens, camera movement, composition.
Assembles the final render prompt FROM assets — never from scratch.

FIX LOG:
  - Added prompt length guard: assembled prompts are truncated to 1800 chars
    before being passed to Pollinations (URL limit ~2048). Character refs are
    summarised rather than dropped to keep consistency.

Shot library: 20 base types × camera movements = 100+ combinations.
Prompt = location_ref + character_refs + wardrobe + state + shot_type + lighting + colour_grade
"""
from __future__ import annotations
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ── Shot Library ─────────────────────────────────────────────────────────────

SHOT_TYPES = {
    # Wide / Context
    "ES":   {"name": "Establishing Shot",  "framing": "extreme wide angle, subject tiny in vast environment, full location visible"},
    "WS":   {"name": "Wide Shot",          "framing": "full body head to toe, subject 40% frame height"},
    "MWS":  {"name": "Medium Wide",        "framing": "knees to head, subject in environment context"},
    # Character
    "MS":   {"name": "Medium Shot",        "framing": "waist to head, subject fills 50% frame"},
    "MCU":  {"name": "Medium Close-Up",    "framing": "chest to head, face readable, shallow DOF"},
    "CU":   {"name": "Close-Up",           "framing": "face fills 70% frame, background blurred"},
    "ECU":  {"name": "Extreme Close-Up",   "framing": "single feature — eyes, hands, mouth — fills frame"},
    # Relational
    "OTS":  {"name": "Over-the-Shoulder",  "framing": "A's shoulder foreground sharp, B's face midground sharp"},
    "TWO":  {"name": "Two-Shot",           "framing": "both characters in frame, each half, eye-level"},
    "GRP":  {"name": "Group Shot",         "framing": "3+ characters visible, arranged in depth"},
    # POV / Insert
    "POV":  {"name": "Point of View",      "framing": "first-person perspective, handheld, slight distortion"},
    "INS":  {"name": "Insert Shot",        "framing": "tight on object/detail, fills frame, extreme shallow DOF"},
    "RXN":  {"name": "Reaction Shot",      "framing": "close-up face registering emotion"},
    # Cinematic
    "LOW":  {"name": "Low Angle",          "framing": "camera below looking up, subject powerful/threatening"},
    "HIGH": {"name": "High Angle",         "framing": "camera above looking down, subject vulnerable"},
    "BIRD": {"name": "Bird's Eye",         "framing": "directly overhead, top-down, subject flat in environment"},
    "DUTCH":{"name": "Dutch Angle",        "framing": "camera tilted 15-30 degrees, psychological unease"},
    "RACK": {"name": "Rack Focus",         "framing": "focus pulls from foreground object to background subject"},
    "SIL":  {"name": "Silhouette",         "framing": "subject backlit, no facial detail, pure shape"},
    "REFL": {"name": "Reflection Shot",    "framing": "subject seen in mirror/window/water, doubled composition"},
}

CAMERA_MOVEMENTS = {
    "STATIC":    "static locked-off camera",
    "PUSH":      "slow dolly push-in toward subject",
    "PULL":      "slow dolly pull-back revealing environment",
    "TRACK":     "lateral tracking shot following subject",
    "PAN":       "horizontal pan across scene",
    "TILT":      "vertical tilt",
    "HANDHELD":  "subtle handheld shake, immersive documentary feel",
    "CRANE":     "sweeping crane move from low to high",
}

LENSES = {
    "wide":    "24mm wide angle, slight distortion, environmental context",
    "normal":  "50mm normal lens, naturalistic perspective",
    "medium":  "85mm medium telephoto, flattering portrait compression",
    "tele":    "135mm telephoto, compressed depth, subject isolated",
    "extreme": "200mm+ extreme telephoto, background defocused to abstraction",
}

EMOTION_TO_SHOT = {
    "dread":      ["MCU", "CU", "DUTCH", "LOW"],
    "revelation": ["ECU", "CU", "RACK", "PUSH"],
    "isolation":  ["WS", "ES", "HIGH", "BIRD"],
    "tension":    ["OTS", "MCU", "TWO", "STATIC"],
    "fear":       ["POV", "HANDHELD", "CU", "LOW"],
    "sadness":    ["MCU", "HIGH", "PULL", "STATIC"],
    "calm":       ["WS", "ES", "STATIC", "MS"],
    "shock":      ["ECU", "INS", "STATIC", "CU"],
}

# Max prompt length for Pollinations URL (safe limit)
MAX_PROMPT_CHARS = 1800


def _pick_shot_sequence(emotional_arc: str, n_shots: int) -> list[str]:
    arc_lower = emotional_arc.lower()
    dominant = "dread"
    for emotion in EMOTION_TO_SHOT:
        if emotion in arc_lower:
            dominant = emotion
            break
    pool = EMOTION_TO_SHOT.get(dominant, ["MS", "MCU", "CU"])
    # Arc: start wide, escalate, end tight
    sequence = ["ES"] + [pool[i % len(pool)] for i in range(n_shots - 2)] + ["CU"]
    return sequence[:n_shots]


def _summarise_char_ref(char: dict, wardrobe: str, state: dict) -> str:
    """
    Build a compact character reference block.
    Full appearance for image consistency, abbreviated state.
    """
    appearance = char.get("appearance", "")
    outfit = wardrobe or ""
    state_note = ""
    if state.get("injuries"):
        state_note += f" [{state['injuries']}]"
    if state.get("fatigue") and state["fatigue"] not in ("none", ""):
        state_note += f" [looks {state['fatigue']}]"
    # Keep outfit to first 120 chars to save URL space
    outfit_short = outfit[:120] + "..." if len(outfit) > 120 else outfit
    return f"[{char['name']}: {appearance} Wearing: {outfit_short}.{state_note}]"


def assemble_prompt(shot: dict, scene: dict, location: dict,
                    characters: list[dict], wardrobes: dict,
                    states: dict, lighting_desc: str, colour_grade: str) -> str:
    """
    Assemble a render prompt entirely from asset registry data.
    Prompts are NEVER manually authored — they are derived from assets.

    Structure:
      [SHOT TYPE] [LOCATION] [CHARACTER refs] [LIGHTING] [COMPOSITION] [COLOUR] [STYLE]

    Capped at MAX_PROMPT_CHARS so Pollinations URL stays within limits.
    """
    shot_type = SHOT_TYPES.get(shot.get("shot_type", "MS"), SHOT_TYPES["MS"])
    lens = LENSES.get(shot.get("lens", "medium"), LENSES["medium"])

    # Location anchor — truncate long descriptions
    loc_ref = location.get("reference_prompt") or location.get("description", "")
    loc_ref = loc_ref[:200] if len(loc_ref) > 200 else loc_ref

    # Character blocks — if too many chars, reduce to name + outfit only
    char_refs = [_summarise_char_ref(c, wardrobes.get(c["id"], ""), states.get(c["id"], {}))
                 for c in characters]
    chars_str = " ".join(char_refs)

    # Hollywood 5 criteria + style suffix (must always be present)
    style_suffix = (
        "Cinematic Hollywood film still, shot on 35mm anamorphic, photoreal, "
        "hyper-detailed, fine film grain, no on-screen text, landscape 16:9."
    )

    core = (
        f"{shot_type['name']}: {shot_type['framing']}. "
        f"{loc_ref}. "
        f"Lighting: {lighting_desc}. "
        f"Depth: blurred foreground, subject sharp midground, atmospheric background. "
        f"Leading lines guide eye to subject. "
        f"Emotion: {shot.get('emotion', 'dread')}. "
        f"Colour grade: {colour_grade}. "
        f"Lens: {lens}. "
        f"{style_suffix}"
    )

    prompt = f"{chars_str} {core}"

    # ── FIX: enforce URL-safe length ──────────────────────────────────────────
    if len(prompt) > MAX_PROMPT_CHARS:
        # Try trimming character blocks first (they're most verbose)
        # Fall back to trimmed appearance (name + first sentence only)
        short_refs = []
        for c in characters:
            appearance_short = c.get("appearance", "").split(".")[0]  # first sentence
            outfit = wardrobes.get(c["id"], "")[:80]
            short_refs.append(f"[{c['name']}: {appearance_short}. Wearing: {outfit}.]")
        chars_str_short = " ".join(short_refs)
        prompt = f"{chars_str_short} {core}"

    # Hard cap — never exceed limit
    return prompt[:MAX_PROMPT_CHARS]


def plan_shots(scene: dict, n_shots: int = 4) -> list[dict]:
    """
    Plan shot types, movements, and lenses for a scene.
    Returns shot specs (without prompts — assembled separately).
    """
    shot_types = _pick_shot_sequence(scene.get("emotional_arc", "dread"), n_shots)

    shots = []
    for i, stype in enumerate(shot_types):
        st = SHOT_TYPES.get(stype, SHOT_TYPES["MS"])
        movement_keys = list(CAMERA_MOVEMENTS.keys())

        if i == 0:
            movement = "STATIC" if stype == "ES" else "PUSH"
        elif i == len(shot_types) - 1:
            movement = "STATIC"
        else:
            movement = movement_keys[i % len(movement_keys)]

        if stype in ("ES", "WS"):
            lens = "wide"
        elif stype in ("CU", "ECU"):
            lens = "tele"
        else:
            lens = "medium"

        # Parse end-emotion from arc string "calm -> dread"
        arc = scene.get("emotional_arc", "dread")
        emotion = arc.split("->")[-1].strip() if "->" in arc else arc.split("→")[-1].strip() if "→" in arc else arc

        shots.append({
            "shot_num":       i + 1,
            "shot_type":      stype,
            "shot_name":      st["name"],
            "framing_note":   st["framing"],
            "camera_movement": movement,
            "lens":           lens,
            "emotion":        emotion.strip() or "dread",
        })
    return shots
