"""
Amadu Studios — Lighting Agent
Assigns motivated lighting setups to each shot based on location, time of day,
weather, emotional arc, and shot type.

Lighting decisions are deterministic from scene metadata — not random.
"""
from __future__ import annotations

SETUPS = {
    "dramatic_night": (
        "dramatic three-point lighting: strong key light from a practical source "
        "(lamp, window, phone screen) at 45 degrees creating half-shadow; "
        "minimal cool fill deepening shadows; thin rim light separating subject "
        "from near-black background"
    ),
    "backlit_silhouette": (
        "powerful backlight from doorway or window creating near-silhouette; "
        "thin separation rim; subject's face in shadow; "
        "background fully exposed and blown-out"
    ),
    "practical_horror": (
        "motivated by a single practical source: a flickering overhead bulb or "
        "a lamp creating a warm pool of amber light; surrounding darkness absolute; "
        "harsh upward shadows below nose and jaw"
    ),
    "interrogation": (
        "single harsh overhead key light, no fill, "
        "deep shadows pooled under eyes brow and chin, "
        "near-black background, face half in shadow"
    ),
    "night_exterior": (
        "cool moonlight as key from directly above creating a cold blue-grey wash; "
        "deep desaturated fill; environment in near-darkness; "
        "rim from a distant street lamp"
    ),
    "golden_dusk": (
        "warm amber sidelight raking in from frame-left at 15 degrees; "
        "long horizontal shadows; soft warm fill from sky; "
        "golden colour cast on skin and surfaces"
    ),
    "overcast_day": (
        "flat overcast diffusion, even soft light from above, "
        "minimal shadows, desaturated daylight quality, "
        "slight cool tint"
    ),
    "fog_exterior": (
        "diffused ambient from fog scatter, no directional key, "
        "all surfaces lit equally, visibility drops at 20 metres, "
        "ghostly cool-white atmosphere"
    ),
    "phone_screen": (
        "cold blue-white phone screen light from below, "
        "underlit face creating unease, "
        "surrounding room in darkness, "
        "hard shadows inverted from natural direction"
    ),
    "reveal_light": (
        "a single beam of motivated light — torch, door crack, or spotlight — "
        "cutting through darkness and landing precisely on the subject; "
        "everything outside the beam is black"
    ),
}

COLOUR_GRADES = {
    "horror_night":   "teal-and-amber grade, crushed blacks, desaturated midtones, deep shadow detail lost",
    "cold_dread":     "cold blue-grey, desaturated to near-monochrome, slight green in shadows",
    "warm_menace":    "warm amber highlights, deep red-brown shadows, desaturated skin tones",
    "overexposed":    "slightly overexposed whites, blown highlights, washed-out colour, clinical feel",
    "vintage_horror": "muted cyan shadows, faded amber highlights, slight halation, film-burnt edges",
    "golden_hour":    "warm orange-yellow cast, rich amber highlights, deep brown shadows",
}


def assign(time_of_day: str, weather: str, emotional_arc: str,
           shot_type: str, scene_objective: str) -> tuple[str, str]:
    """
    Return (lighting_description, colour_grade) for a shot.
    Decision tree based on scene metadata.
    """
    arc_lower = (emotional_arc + " " + scene_objective).lower()
    time_lower = time_of_day.lower()
    weather_lower = weather.lower()

    # Colour grade
    if "fog" in weather_lower:
        grade = "cold_dread"
    elif time_lower in ("night", "dusk"):
        grade = "horror_night"
    elif "dawn" in time_lower:
        grade = "golden_hour"
    elif "reveal" in arc_lower or "discovery" in arc_lower:
        grade = "vintage_horror"
    else:
        grade = "horror_night"

    # Lighting setup
    if "fog" in weather_lower and "exterior" in arc_lower:
        setup = "fog_exterior"
    elif time_lower == "night" and "exterior" in arc_lower:
        setup = "night_exterior"
    elif "phone" in arc_lower or "screen" in arc_lower:
        setup = "phone_screen"
    elif "reveal" in arc_lower or "discovers" in arc_lower:
        setup = "reveal_light"
    elif shot_type in ("CU", "ECU", "OTS") and time_lower == "night":
        setup = "interrogation"
    elif time_lower in ("dusk", "dawn"):
        setup = "golden_dusk"
    elif time_lower == "day" and "overcast" in weather_lower:
        setup = "overcast_day"
    elif "silhouette" in arc_lower or shot_type == "SIL":
        setup = "backlit_silhouette"
    else:
        setup = "dramatic_night"

    return SETUPS[setup], COLOUR_GRADES[grade]
