"""
Amadu Studios — Writer Agent
Generates screenplay dialogue + narration for a part, reading character
voices from the database. Saves screenplay lines to DB.

FIX LOG:
  - recap_for_next is now saved to the NEXT episode's recap field in the DB.
    Previously it was generated but thrown away, breaking story continuity for Parts 2+.
  - Voice ID lookup is now case-insensitive and matches on first-name if full name fails.
"""
from __future__ import annotations
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from amadu_studios.database import db
from amadu_studios.agents import llm
import config as cfg

SYSTEM = cfg.BRAND_SYSTEM_PROMPT + """

ADDITIONAL RULES FOR AMADU STUDIOS:
- Characters must match their registered appearance exactly — never contradict the character bible.
- Dialogue should be sparse and purposeful. Every line advances tension or character.
- The Narrator speaks between scenes — keep it brief and atmospheric.
- Do not write stage directions in parentheses inside the text field.
"""


def _match_voice(speaker: str, voice_map: dict, fallback: str) -> str:
    """Case-insensitive match; also tries first-name-only match."""
    up = speaker.upper().strip()
    if up in voice_map:
        return voice_map[up]
    # Try first word
    first = up.split()[0] if up else up
    for k, v in voice_map.items():
        if k.startswith(first):
            return v
    return fallback


def run(prod_id: int, ep_id: int, part_num: int) -> list[dict]:
    """Generate the screenplay for this part and save to DB."""
    prod      = db.get_production(prod_id)
    episode   = db.get_episode(prod_id, part_num)
    scenes    = db.get_scenes(ep_id)
    characters = db.get_characters(prod_id)

    lo, hi = cfg.PART_WORDS
    total_parts = prod.get("total_parts", 20)
    is_finale = part_num == total_parts

    char_brief = "\n".join(
        f"  - {c['name']} ({c['role']}): {c['appearance']}"
        for c in characters)

    scene_summaries = "\n".join(
        f"  Scene {s['scene_num']}: {s['objective']} | Emotional arc: {s['emotional_arc']}"
        for s in scenes)

    finale_note = ("This is the FINALE — bring the story to a satisfying, eerie, ambiguous resolution."
                   if is_finale else f"End Part {part_num} on a strong cliffhanger.")

    prompt = f"""Write the screenplay for Part {part_num} of {total_parts} of "{prod['title']}".

Characters (appearance locked — do not contradict):
{char_brief}

Scene breakdown from Director:
{scene_summaries}

Recap of previous part: {episode.get('recap', '(this is Part 1)')}
{finale_note}

Return ONLY this JSON:
{{
  "lines": [
    {{"speaker": "Narrator|<exact character name from list above>", "text": "spoken line, no stage directions"}}
  ],
  "youtube_title": "{prod['title']} — Part {part_num}: <hooky subtitle, total under 70 chars>",
  "youtube_description": "2-3 sentences. Include: horror, scary story, nosleep, original fiction. End with: Subscribe for daily parts.",
  "hashtags": ["horror","scarystories","nosleep","horrortok","storytime","creepy","psychologicalhorror"],
  "thumbnail_text": "2-4 PUNCHY UPPERCASE WORDS",
  "tiktok_caption": "under 150 chars ending on a curiosity hook",
  "pinned_comment": "engagement question about this part",
  "recap_for_next": "1-2 sentence recap of Part {part_num} for use at the top of Part {part_num + 1}. Keep it tight."
}}

Target {lo}-{hi} total words across all lines. Grounded psychological horror. No gore."""

    data = llm.gen_json(SYSTEM, prompt)

    lines = data.get("lines", [])
    # Build voice map — keys uppercased for case-insensitive matching
    voice_map = {c["name"].upper(): c["voice_id"] for c in characters}
    for line in lines:
        spk = line.get("speaker", "Narrator")
        line["voice_id"] = _match_voice(spk, voice_map, cfg.TTS_VOICE)

    db.save_screenplay(ep_id, lines)
    db.update_episode(ep_id,
        youtube_title=data.get("youtube_title", f"{prod['title']} — Part {part_num}"),
        youtube_desc=data.get("youtube_description", ""),
        hashtags=json.dumps(data.get("hashtags", [])),
        thumbnail_text=data.get("thumbnail_text", ""),
        pinned_comment=data.get("pinned_comment", ""),
        status="scripted",
    )

    # ── FIX: save recap to the NEXT part so continuity works ──────────────────
    recap = data.get("recap_for_next", "").strip()
    if recap and not is_finale:
        next_ep = db.get_episode(prod_id, part_num + 1)
        if next_ep:
            db.update_episode(next_ep["id"], recap=recap)
            print(f"[writer] saved recap to Part {part_num + 1}")

    word_count = sum(len(l.get("text", "").split()) for l in lines)
    print(f"[writer] part {part_num}: {len(lines)} lines, ~{word_count} words")
    return lines
