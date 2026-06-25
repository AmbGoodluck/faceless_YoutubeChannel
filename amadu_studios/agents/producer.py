"""
Amadu Studios — Producer Agent
Creates the production bible and populates all asset registries in the database.
The Producer runs ONCE per production and never again.

Output:
  - productions record
  - characters records (with locked appearance + wardrobe)
  - locations records
  - episode beat plan (all parts)
"""
from __future__ import annotations
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from amadu_studios.database import db
from amadu_studios.agents import llm

SYSTEM = """\
You are the Executive Producer of Amadu Studios, an AI-native film studio.
You create production bibles for serialized horror/drama content for YouTube.
Your output feeds directly into asset registries — it must be precise, visual, and consistent.

CHARACTER RULE: Every character needs an appearance description precise enough that an
image model can reproduce the same face and body across 100+ shots. Include exact height,
build, skin tone, hair, eyes, and distinguishing features. Costumes must be specific enough
to recreate from memory: fabrics, colours, fit, shoes.

LOCATION RULE: Every location needs a reference prompt that Pollinations.ai can use to
generate a consistent environmental establishing shot.
"""


def run(title: str = None, genre: str = "horror", parts: int = 20,
        existing_prod_id: int = None) -> dict:
    """Create a new production (or return the existing one if ID provided)."""
    db.init()

    if existing_prod_id:
        prod = db.get_production(existing_prod_id)
        if prod:
            print(f"[producer] using existing production #{existing_prod_id}: {prod['title']}")
            return prod

    prompt = f"""Create a complete production bible for a serialized {genre} YouTube series.
{"Title: " + title if title else "Invent a compelling original title."}
Format: {parts} parts of 5-6 minutes each. One part per day. Each part ends on a cliffhanger.

Return ONLY this JSON:
{{
  "title": "series title",
  "genre": "{genre}",
  "logline": "one gripping sentence — the central mystery or dread",
  "setting": "specific city, neighbourhood, time of year — vivid and distinctive",
  "target_audience": "teens and young adults 16-30",
  "style_pack": "horror",
  "characters": [
    {{
      "name": "full name",
      "role": "protagonist|antagonist|ally|antagonist-ally",
      "gender": "male|female",
      "appearance": "Precise physical description: exact height (e.g. 5ft 8), build (slim/athletic/stocky/heavyset), skin tone (specific, e.g. warm dark brown / pale freckled / olive), hair (colour, texture, length, style), eyes (colour, shape), and 1-2 distinctive features (scar, birthmark, specific posture, etc.). Write as a casting brief. 3-4 sentences.",
      "default_outfit": "Specific clothing: name every item with colour, fabric, fit. E.g. 'worn rust-orange knit sweater, dark olive cargo trousers with side pockets, white canvas sneakers scuffed at the toe, silver stud earrings'. This is the locked costume for the series."
    }}
  ],
  "locations": [
    {{
      "name": "location name",
      "description": "what the location is and its atmosphere",
      "palette": "cinematic colour grade — e.g. teal-and-amber with crushed blacks",
      "time_of_day": "night|day|dusk|dawn",
      "weather": "clear|rain|fog|overcast",
      "reference_prompt": "A cinematic establishing shot of [location]: [describe architecture, lighting, atmosphere, colour, mood in 2-3 sentences for an image generator]"
    }}
  ],
  "parts": [
    {{
      "n": 1,
      "beat": "what happens in Part 1 — specific plot beat advancing the central mystery. Part {parts} must resolve the story."
    }}
  ]
}}

Include 2-4 main characters, 3-5 key locations, and exactly {parts} parts.
Make it genuinely unsettling through psychological dread. No gore. Advertiser-safe."""

    data = llm.gen_json(SYSTEM, prompt)

    # Create production record
    prod_id = db.create_production(
        title=data["title"],
        genre=data.get("genre", genre),
        logline=data.get("logline", ""),
        setting=data.get("setting", ""),
        total_parts=parts,
        style_pack=data.get("style_pack", "horror"),
    )
    print(f"[producer] created production #{prod_id}: {data['title']}")

    # Register characters + default wardrobes
    import config as cfg
    male_voices = list(cfg.MALE_VOICES)
    female_voices = list(cfg.FEMALE_VOICES)

    for c in data.get("characters", []):
        pool = female_voices if c.get("gender","").lower().startswith("f") else male_voices
        voice = pool.pop(0) if pool else cfg.TTS_VOICE
        char_id = db.upsert_character(
            prod_id=prod_id,
            name=c["name"],
            role=c.get("role", ""),
            gender=c.get("gender", ""),
            appearance=c.get("appearance", ""),
            voice_id=voice,
        )
        db.set_wardrobe(
            char_id=char_id,
            label="default",
            outfit=c.get("default_outfit", ""),
            part_from=1,
            part_to=999,
        )
        print(f"[producer]   character: {c['name']} ({c.get('role')}) -> voice: {voice}")

    # Register locations
    for loc in data.get("locations", []):
        db.upsert_location(
            prod_id=prod_id,
            name=loc["name"],
            description=loc.get("description", ""),
            palette=loc.get("palette", "teal-and-amber, crushed blacks"),
            time_of_day=loc.get("time_of_day", "night"),
            weather=loc.get("weather", "clear"),
            reference_prompt=loc.get("reference_prompt", ""),
        )
        print(f"[producer]   location: {loc['name']}")

    # Store all part beats as episode stubs
    for part in data.get("parts", []):
        db.create_episode(
            prod_id=prod_id,
            part_num=part["n"],
            title=f"{data['title']} — Part {part['n']}",
            beat=part.get("beat", ""),
        )

    prod = db.get_production(prod_id)
    print(f"[producer] production bible complete: {prod_id}")
    return prod


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
