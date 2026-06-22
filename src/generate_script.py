"""
Stage 2 — Script generation via Google Gemini (FREE tier, no credit card).
Get a key at https://aistudio.google.com/apikey and put it in .env as GEMINI_API_KEY.

Output: outputs/<id>-<slug>/script.json  (+ script.txt for the approval checkpoint)
"""
import os, sys, json, re, time, requests

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
            "maxOutputTokens": 16384,
            "responseMimeType": "application/json",
            # 2.5 models burn output budget on hidden "thinking" tokens, which
            # truncates the JSON. Turn it off so the full script comes back.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    r = None
    for attempt in range(5):
        r = requests.post(
            config.GEMINI_ENDPOINT,
            params={"key": os.environ["GEMINI_API_KEY"]},
            json=body, timeout=120,
        )
        if r.status_code in (429, 500, 502, 503, 504):   # transient — back off and retry
            wait = 5 * (attempt + 1)
            print(f"[gemini] {r.status_code}, retrying in {wait}s...")
            time.sleep(wait)
            continue
        break
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


def gen_json(system: str, user: str, attempts: int = 8) -> dict:
    """Call Gemini and parse JSON, retrying every 5s until it succeeds (LLMs sometimes
    emit a malformed character in long outputs). Raises only after `attempts` tries."""
    import requests as _rq
    last = None
    for i in range(attempts):
        try:
            return json.loads(_extract_json(_call_gemini(system, user)))
        except (json.JSONDecodeError, KeyError, RuntimeError, _rq.RequestException) as e:
            last = e
            print(f"[gemini] response not usable (try {i+1}/{attempts}): {e}; retrying in 5s")
            time.sleep(5)
    raise RuntimeError(f"Gemini failed to return valid JSON after {attempts} tries: {last}")


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
  "scene_prompts": array of {config.SCENES_PER_VIDEO} visual descriptions IN STORY ORDER, one per
                   narration beat (beat 1 = the opening line, last = the ending). Each MUST depict
                   the story's named character(s) as realistic people — say who they are (approx age,
                   look, clothing), what they are doing, and the exact location/object the narration
                   mentions at that moment, so the image matches what is being said. Keep it dark and
                   cinematic. No on-screen text or letters in the image.
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


def generate_episode(spec: dict) -> dict:
    """Generate one 6-8 min serialized episode from a story spec (see src/story.py)."""
    lo, hi = config.EPISODE_WORDS
    chars = ", ".join(f"{c.get('name')} ({c.get('role')})" for c in spec.get("characters", []))
    recap = spec.get("recap") or "(this is the first episode — no recap yet)"
    finale = ("This is the FINALE — bring the story to a satisfying, eerie resolution."
              if spec.get("is_finale") else "End on a strong cliffhanger for the next episode.")
    user_prompt = f"""Write Episode {spec['episode']} of {spec['total']} of the horror series "{spec['story_title']}".
Logline: {spec.get('logline','')}
Setting: {spec.get('setting','')}
Characters: {chars}
Story so far (recap of previous episodes): {recap}
WHAT THIS EPISODE COVERS: {spec['beat']}
{finale}

Return ONLY a JSON object with these keys:
  "narration": the full episode voiceover, {lo}-{hi} words, third person past tense, grounded teen
               horror, NO gore. If episode > 1, open with a 1-2 sentence "Previously..." recap, then
               tell this episode and end on the beat above.
  "scene_prompts": array of {config.SCENES_PER_VIDEO} visual descriptions IN STORY ORDER (one per beat
               of the narration, start to finish). Each shows the named character(s) as realistic
               people doing the action at that moment, dark cinematic, no on-screen text.
  "youtube_title": "{spec['story_title']} — Ep {spec['episode']}: <hooky subtitle>" under 70 chars
  "youtube_description": 2-3 sentences with search keywords + a subscribe CTA, ending with an
               "original fiction" note
  "hashtags": array of 10-12 tags (no # symbol) mixing broad horror tags, niche tags, and the series name
  "tiktok_caption": under 150 chars, teases THIS episode, ends on a curiosity hook
  "thumbnail_text": 2-4 punchy uppercase words for the thumbnail
  "pinned_comment": one engagement-bait question about this episode
  "recap_for_next": 1-2 sentences summarizing what happened this episode (fed into the next one)"""

    data = gen_json(config.BRAND_SYSTEM_PROMPT, user_prompt)

    sid, ep = spec["story_id"], spec["episode"]
    data["id"] = f"{sid}.{ep}"
    data["title"] = data.get("youtube_title", f"{spec['story_title']} Ep {ep}")
    slug = f"s{sid}e{ep:02d}-{slugify(spec['story_title'])}"
    data["slug"] = slug

    out_dir = os.path.join(config.OUTPUT_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "script.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(out_dir, "narration.txt"), "w") as f:
        f.write(data["narration"])
    with open(os.path.join(out_dir, "script.txt"), "w") as f:
        f.write(f"{data['title']}\n\n{data['narration']}\n\n--- SCENES ---\n")
        f.write("\n".join(f"{i+1}. {s}" for i, s in enumerate(data.get("scene_prompts", []))))
    print(f"[script] {slug} ({len(data['narration'].split())} words)")
    return data


if __name__ == "__main__":
    from src import story
    generate_episode(story.next_episode_spec())
