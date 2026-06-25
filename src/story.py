"""
Serialized-story manager. Tracks which story + part we're on, generates a full
story "bible" (characters with locked appearance/costume, scene arcs) when a new
story starts, and returns the next part's spec to the script generator.

State persists in story_state.json (committed by the cloud workflow).

Format: "Parts" — each Part is 5–6 min. One Part per day. Story runs for
PARTS_PER_STORY parts (e.g. 20), then a new story starts with Part 1.

Character consistency is enforced via the bible: every character has a locked
`appearance` and `costume` that gets injected verbatim into every shot prompt
they appear in — preventing visual drift across parts.
"""
from __future__ import annotations
import os, sys, json, re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import generate_script   # reuse gen_json + _call_llm

STATE = "story_state.json"

BIBLE_SYSTEM = """\
You are the show-runner for "Lights Out Tales", a faceless YouTube horror series.
You invent original, serialized horror stories — grounded, eerie, psychological, NO gore,
advertiser-safe. Each story is structured like a Netflix limited series: it unfolds across
multiple 5–6 minute "Parts", building tension across every part, with each Part ending on
a cliffhanger. The finale resolves the story with an ambiguous, eerie conclusion.

CHARACTER CONSISTENCY RULE: Every character must have a detailed physical description and
a locked costume per story arc. These descriptions will be injected into every image prompt
they appear in, ensuring visual consistency across all parts of the story.
"""


def _load():
    return json.load(open(STATE)) if os.path.exists(STATE) else None


def _save(st):
    json.dump(st, open(STATE, "w"), indent=2, ensure_ascii=False)


def _gen_bible() -> dict:
    n = config.PARTS_PER_STORY
    prompt = f"""Invent a NEW original horror story for "Lights Out Tales".
It will unfold across up to {n} parts (5–6 min each). Plan the arc.

Return ONLY this JSON structure:
{{
  "story_title": "short, hooky series title (3-5 words)",
  "logline": "one sentence that sets up the central mystery or dread",
  "setting": "specific time and place — city, neighbourhood, time of year",
  "characters": [
    {{
      "name": "character full name",
      "role": "brief role (e.g. protagonist, antagonist, ally)",
      "gender": "male|female",
      "appearance": "detailed physical description: exact height, build (slim/athletic/stocky/etc), skin tone, hair colour and style, eye colour, distinctive facial features — written as a cinematographer would describe them for a casting brief. 2–3 sentences.",
      "costume": "locked outfit for this story arc: specific clothing items, colours, materials, footwear. This is what they wear throughout the story unless a change is dramatic plot point."
    }}
  ],
  "parts": [
    {{
      "n": 1,
      "beat": "what happens in this part, advancing the arc; the last part must resolve the story"
    }}
  ]
}}

Include 2–4 main characters. Plan {n} parts total — the last part is the finale.
Make the story genuinely unsettling through psychological dread, not gore."""

    bible = generate_script.gen_json(BIBLE_SYSTEM, prompt)

    # Assign a distinct, consistent TTS voice to each character.
    male = list(config.MALE_VOICES)
    female = list(config.FEMALE_VOICES)
    vm = {}
    for c in bible.get("characters", []):
        pool = female if str(c.get("gender", "")).lower().startswith("f") else male
        vm[c["name"].upper()] = pool.pop(0) if pool else config.TTS_VOICE
    bible["voice_map"] = vm
    return bible


def next_part_spec() -> dict:
    """Return the spec for the NEXT part. Does NOT advance the counter — call
    commit() only after the part is successfully generated. The story bible IS
    persisted immediately so retries reuse it and don't regenerate."""
    st = _load()
    if not st or st.get("part", 0) >= config.PARTS_PER_STORY:
        story_id = (st.get("story_id", 0) + 1) if st else 1
        bible = _gen_bible()
        st = {"story_id": story_id, "part": 0, "bible": bible, "last_recap": ""}
        _save(st)
        print(f"[story] new story #{story_id}: {bible.get('story_title')}")

    n = st["part"] + 1          # the part we're about to make
    bible = st["bible"]
    parts = bible.get("parts", [])
    beat = parts[n - 1]["beat"] if n - 1 < len(parts) else "continue the story"
    total = len(parts)

    # Build a character reference dict: {NAME_UPPER: "appearance. Wearing: costume."}
    char_refs = {}
    for c in bible.get("characters", []):
        name_key = c["name"].upper()
        appearance = c.get("appearance", "")
        costume = c.get("costume", "")
        char_refs[name_key] = f"{appearance} Wearing: {costume}."

    return {
        "story_id":    st["story_id"],
        "part":        n,
        "total":       total,
        "story_title": bible.get("story_title", "Untitled"),
        "logline":     bible.get("logline", ""),
        "setting":     bible.get("setting", ""),
        "characters":  bible.get("characters", []),
        "char_refs":   char_refs,
        "voice_map":   bible.get("voice_map", {}),
        "beat":        beat,
        "recap":       st.get("last_recap", ""),
        "is_finale":   n == total,
    }


def commit(recap: str):
    """Mark the current part as done (advance counter) and store its recap."""
    st = _load()
    if st:
        st["part"] += 1
        st["last_recap"] = recap or ""
        _save(st)


# ── backward-compat aliases ──────────────────────────────────────────────────
def next_episode_spec() -> dict:
    return next_part_spec()

def save_recap(recap: str):
    commit(recap)


if __name__ == "__main__":
    print(json.dumps(next_part_spec(), indent=2))
