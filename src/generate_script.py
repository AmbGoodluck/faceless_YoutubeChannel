"""
Stage 2 — Script generation via Google Gemini (FREE tier, no credit card).
Get a key at https://aistudio.google.com/apikey and put it in .env as GEMINI_API_KEY.

Output: outputs/<id>-<slug>/script.json  (+ script.txt for the approval checkpoint)
"""
import os, sys, json, re, requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def _call_gemini(system: str, user: str) -> str:
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            # 2.5 models burn output budget on hidden "thinking" tokens, which
            # truncates the JSON. Turn it off so the full script comes back.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    r = requests.post(
        config.GEMINI_ENDPOINT,
        params={"key": os.environ["GEMINI_API_KEY"]},
        json=body, timeout=120,
    )
    r.raise_for_status()
    cand = r.json()["candidates"][0]
    if cand.get("finishReason") == "MAX_TOKENS":
        raise RuntimeError("Gemini hit the token limit; raise maxOutputTokens.")
    return cand["content"]["parts"][0]["text"]


def _extract_json(raw: str) -> str:
    """Strip code fences and grab the outermost {...} so stray text can't break parsing."""
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end + 1] if start != -1 and end != -1 else raw


def generate(row: dict) -> dict:
    lo, hi = config.SHORTFORM_WORDS
    user_prompt = f"""\
Write one short-form episode of Lights Out Tales.

TITLE: {row['title']}
REQUIRED OPENING LINE (use as the first sentence, lightly polish if needed):
"{row['hook_opening']}"
PREMISE & REQUIRED ENDING BEAT:
{row['premise']}

Return ONLY a JSON object with exactly these keys:
  "narration": full voiceover script, {lo}-{hi} words, plain spoken sentences
  "scene_prompts": array of {config.SCENES_PER_VIDEO} short visual descriptions, one per beat,
                   each a concrete dark cinematic image with NO people's faces and NO text
  "youtube_title": viral curiosity-gap title under 70 chars (no clickbait lies); make people NEED to click
  "youtube_description": 2-3 sentences with naturally woven search keywords (scary story, true horror,
                         creepy, nosleep) and a subscribe CTA, ending with an "original fiction" note
  "hashtags": array of 10-12 tags without the # symbol, mixing broad (horror, scarystories, creepy)
              and niche (nosleep, horrortok, storytime) tags
  "tiktok_caption": under 150 chars, ends on a curiosity hook
  "thumbnail_text": 2-4 punchy words for the YouTube thumbnail (uppercase impact, e.g. "SHE WASN'T ALONE")
  "pinned_comment": one short engagement-bait question to pin in the comments (drives replies)"""

    raw = _call_gemini(config.BRAND_SYSTEM_PROMPT, user_prompt)
    data = json.loads(_extract_json(raw))

    data["id"] = row["id"]
    data["title"] = row["title"]
    slug = f"{row['id']}-{slugify(row['title'])}"

    out_dir = os.path.join(config.OUTPUT_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "script.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # narration.txt is the EDITABLE source of truth for the voiceover. Edit this
    # file (plain text, no JSON) and the next --render uses your version.
    with open(os.path.join(out_dir, "narration.txt"), "w") as f:
        f.write(data["narration"])
    with open(os.path.join(out_dir, "script.txt"), "w") as f:
        f.write(f"{data['title']}\n\n{data['narration']}\n\n--- SCENES ---\n")
        f.write("\n".join(f"{i+1}. {s}" for i, s in enumerate(data["scene_prompts"])))

    print(f"[script] {slug} -> {out_dir}/script.json")
    return data


def load_narration(out_dir: str) -> str:
    """Prefer the editable narration.txt so the user's edits take effect."""
    txt = os.path.join(out_dir, "narration.txt")
    if os.path.exists(txt):
        with open(txt) as f:
            return f.read().strip()
    with open(os.path.join(out_dir, "script.json")) as f:
        return json.load(f)["narration"]


if __name__ == "__main__":
    generate({
        "id": "1", "title": "The Note on the Windshield",
        "hook_opening": "The note under Maya's wiper said 'you forgot to lock the back door.' She lived on the fourth floor.",
        "premise": "A woman finds a handwritten note that's correct about something no one should know. Ends: a second note is already waiting inside her apartment.",
        "notes": "",
    })
