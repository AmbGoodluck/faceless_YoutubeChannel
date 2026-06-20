"""
Stage 2 — Script generation.
Turns a queue row (title + hook + premise) into a finished, brand-voice horror
script plus everything the video tool and the platforms need.

Output: outputs/<id>-<slug>/script.json
"""
import os, sys, json, re
import anthropic

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def generate(row: dict) -> dict:
    """row keys: id, title, hook_opening, premise, notes"""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    lo, hi = config.SHORTFORM_WORDS
    user_prompt = f"""\
Write one short-form episode of Lights Out Tales.

TITLE: {row['title']}
REQUIRED OPENING LINE (use as the first sentence, lightly polish if needed):
"{row['hook_opening']}"
PREMISE & REQUIRED ENDING BEAT:
{row['premise']}

Return ONLY valid JSON (no markdown fence) with exactly these keys:
{{
  "narration": "the full voiceover script, {lo}-{hi} words, plain spoken sentences",
  "scene_prompts": [ {config.SCENES_PER_VIDEO} short visual descriptions, one per beat,
                     each a concrete dark cinematic image with NO people's faces ],
  "youtube_title": "click-worthy title under 70 chars",
  "youtube_description": "2-3 sentence description, original-fiction disclaimer at the end",
  "hashtags": ["8-12 relevant tags without the # symbol"],
  "tiktok_caption": "under 150 chars, ends with a curiosity hook"
}}"""

    msg = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=2000,
        system=config.BRAND_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
    data = json.loads(raw)

    data["id"] = row["id"]
    data["title"] = row["title"]
    slug = f"{row['id']}-{slugify(row['title'])}"

    out_dir = os.path.join(config.OUTPUT_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "script.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # human-readable copy for the script-approval checkpoint
    with open(os.path.join(out_dir, "script.txt"), "w") as f:
        f.write(f"{data['title']}\n\n{data['narration']}\n\n--- SCENES ---\n")
        f.write("\n".join(f"{i+1}. {s}" for i, s in enumerate(data["scene_prompts"])))

    print(f"[script] {slug} -> {out_dir}/script.json")
    return data


if __name__ == "__main__":
    # quick manual test with episode 1
    demo = {
        "id": "1", "title": "The Note on the Windshield",
        "hook_opening": "The note under Maya's wiper said 'you forgot to lock the back door.' She lived on the fourth floor.",
        "premise": "A woman finds a handwritten note that's correct about something no one should know. Ends: a second note is already waiting inside her apartment.",
        "notes": "",
    }
    generate(demo)
