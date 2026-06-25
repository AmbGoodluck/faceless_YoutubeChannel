"""
Amadu Studios — Director Agent
Converts a part's beat into Scene DNA and saves scenes to the database.

FIX LOG:
  - Added scene deduplication: re-running a part deletes existing scenes first.
  - Added ID validation: invalid location_id / character_ids are clamped to valid values
    instead of silently inserting garbage, which would crash the renderer later.
  - Added validation retry: if LLM returns a scene with no valid characters, we insert
    the protagonist automatically so we always have at least one character per scene.
"""
from __future__ import annotations
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from amadu_studios.database import db
from amadu_studios.agents import llm

SYSTEM = """\
You are the Director of Amadu Studios. You convert screenplay beats into structured
Scene DNA — precise production documents that downstream agents (storyboard, cinematographer,
lighting) use to plan every shot.

You MUST use ONLY the integer IDs listed in the asset registry below.
Do NOT invent new characters or locations. Do NOT use names — use the numeric IDs only.
Every decision is motivated by story logic.
"""


def _valid_loc_id(raw, valid_ids: list[int]) -> int:
    """Clamp LLM-returned location_id to a valid DB integer."""
    try:
        val = int(raw)
        if val in valid_ids:
            return val
    except (TypeError, ValueError):
        pass
    return valid_ids[0]  # fallback: first registered location


def _valid_char_ids(raw, valid_ids: list[int]) -> list[int]:
    """Filter LLM-returned character_ids to only valid DB integers."""
    result = []
    for x in (raw or []):
        try:
            v = int(x)
            if v in valid_ids:
                result.append(v)
        except (TypeError, ValueError):
            pass
    return result or [valid_ids[0]]  # always at least one character


def run(prod_id: int, ep_id: int, part_num: int) -> list[dict]:
    """Generate Scene DNA for all scenes in this part and save to DB."""
    prod = db.get_production(prod_id)
    episode = db.get_episode(prod_id, part_num)
    characters = db.get_characters(prod_id)
    locations = db.get_locations(prod_id)

    valid_loc_ids  = [l["id"] for l in locations]
    valid_char_ids = [c["id"] for c in characters]

    # Dedup: delete existing scenes for this episode so re-runs are idempotent
    with db.tx() as conn:
        existing = conn.execute("SELECT id FROM scenes WHERE episode_id=?", (ep_id,)).fetchall()
        if existing:
            scene_ids = [r["id"] for r in existing]
            # Also delete shots belonging to these scenes
            for sid in scene_ids:
                conn.execute("DELETE FROM shots WHERE scene_id=?", (sid,))
            conn.execute("DELETE FROM scenes WHERE episode_id=?", (ep_id,))
            print(f"[director] cleared {len(existing)} existing scenes for ep {ep_id}")

    char_list = "\n".join(f"  - ID {c['id']}: {c['name']} ({c['role']})" for c in characters)
    loc_list  = "\n".join(f"  - ID {l['id']}: {l['name']} — {l['description'][:80]}" for l in locations)

    prompt = f"""Production: "{prod['title']}"
Part {part_num} beat: {episode['beat']}
Recap of previous part: {episode.get('recap', '(this is Part 1)')}

Available characters (use numeric IDs only):
{char_list}

Available locations (use numeric IDs only):
{loc_list}

Break this part into 4-6 scenes. Return ONLY this JSON:
{{
  "scenes": [
    {{
      "scene_num": 1,
      "location_id": <integer ID from list above>,
      "time_of_day": "night|day|dusk|dawn",
      "weather": "clear|rain|fog|overcast",
      "objective": "what must happen in this scene for the story to advance",
      "emotional_arc": "opening emotion -> closing emotion (e.g. calm -> dread)",
      "character_ids": [<integer IDs from list above — only characters present in this scene>],
      "prop_ids": [],
      "dialogue_summary": "1-2 sentences of what's said/done — feeds the Writer"
    }}
  ]
}}

IMPORTANT: use ONLY the integer IDs shown above. Do not invent new IDs."""

    data = llm.gen_json(SYSTEM, prompt)
    saved = []
    for s in data.get("scenes", []):
        loc_id   = _valid_loc_id(s.get("location_id"), valid_loc_ids)
        char_ids = _valid_char_ids(s.get("character_ids", []), valid_char_ids)

        scene_id = db.create_scene(
            ep_id=ep_id,
            scene_num=s["scene_num"],
            location_id=loc_id,
            time_of_day=s.get("time_of_day", "night"),
            weather=s.get("weather", "clear"),
            objective=s.get("objective", ""),
            emotional_arc=s.get("emotional_arc", "dread"),
            character_ids=char_ids,
            prop_ids=s.get("prop_ids", []),
        )
        saved.append(scene_id)
        char_names = [c["name"] for c in characters if c["id"] in char_ids]
        loc_name   = next((l["name"] for l in locations if l["id"] == loc_id), str(loc_id))
        print(f"[director] scene {s['scene_num']} -> #{scene_id} | {loc_name} | chars: {char_names}")

    return db.get_scenes(ep_id)
