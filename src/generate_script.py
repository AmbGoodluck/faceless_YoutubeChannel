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
    # Gentle exponential backoff. ONE retry layer (gen_json no longer re-calls on
    # transient errors), so we don't torch the free-tier daily request quota.
    delay, last = 10, None
    for attempt in range(7):
        try:
            r = requests.post(
                config.GEMINI_ENDPOINT,
                params={"key": os.environ["GEMINI_API_KEY"]},
                json=body, timeout=120,
            )
        except requests.RequestException as e:                  # network blip
            last = e
            print(f"[gemini] network error: {e}; retry in {delay}s")
            time.sleep(delay); delay = min(delay * 2, 120); continue
        if r.status_code in (429, 500, 502, 503, 504):          # transient — back off
            ra = r.headers.get("Retry-After")
            wait = int(ra) if (ra and ra.isdigit()) else delay
            print(f"[gemini] {r.status_code}; backing off {wait}s (attempt {attempt+1}/7)")
            time.sleep(wait); delay = min(delay * 2, 120); last = r; continue
        r.raise_for_status()
        cand = r.json()["candidates"][0]
        if cand.get("finishReason") == "MAX_TOKENS":
            raise RuntimeError("Gemini hit the token limit; raise maxOutputTokens.")
        return cand["content"]["parts"][0]["text"]
    code = getattr(last, "status_code", "network")
    raise RuntimeError(
        f"Gemini unavailable after 7 backoffs (last={code}). This is almost always the "
        "free-tier DAILY request quota — wait for the daily reset (~midnight Pacific) or "
        "enable pay-as-you-go billing on the API key (Flash costs pennies).")


def _call_claude(system: str, user: str) -> str:
    """Anthropic Messages API. Raw HTTP (no SDK dependency). Returns the text body."""
    body = {
        "model": config.CLAUDE_MODEL,
        "max_tokens": config.CLAUDE_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content":
                      user + "\n\nReturn ONLY the JSON object — no prose, no markdown fences."}],
    }
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — add it to .env (local) and as a "
                           "GitHub Actions secret. This pipeline is Claude-only; there is no fallback.")
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    delay, last = 5, None
    for attempt in range(7):
        try:
            r = requests.post(config.CLAUDE_ENDPOINT, headers=headers, json=body, timeout=180)
        except requests.RequestException as e:
            last = e
            print(f"[claude] network error: {e}; retry in {delay}s")
            time.sleep(delay); delay = min(delay * 2, 120); continue
        if r.status_code in (429, 500, 502, 503, 529):          # rate-limited / overloaded
            ra = r.headers.get("retry-after")
            wait = int(ra) if (ra and ra.isdigit()) else delay
            print(f"[claude] {r.status_code}; backing off {wait}s (attempt {attempt+1}/7)")
            time.sleep(wait); delay = min(delay * 2, 120); last = r; continue
        r.raise_for_status()
        data = r.json()
        if data.get("stop_reason") == "max_tokens":
            raise RuntimeError("Claude hit max_tokens; raise CLAUDE_MAX_TOKENS.")
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    code = getattr(last, "status_code", "network")
    raise RuntimeError(f"Claude API unavailable after 7 backoffs (last={code}). "
                       "Check the ANTHROPIC_API_KEY and that the account has credit.")


def _call_llm(system: str, user: str) -> str:
    """Claude only — Gemini has been removed from the active path."""
    return _call_claude(system, user)


def _extract_json(raw: str) -> str:
    """Strip code fences and grab the outermost {...} so stray text can't break parsing."""
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end + 1] if start != -1 and end != -1 else raw


def gen_json(system: str, user: str, attempts: int = 3) -> dict:
    """Parse Gemini's JSON, regenerating only when the *content* is malformed.
    Transient HTTP errors are handled inside _call_gemini (with backoff), so we do
    NOT re-call here on those — that's what was burning the daily quota."""
    last = None
    for i in range(attempts):
        try:
            return json.loads(_extract_json(_call_llm(system, user)))
        except (json.JSONDecodeError, KeyError) as e:        # 200 OK but bad JSON -> regenerate
            last = e
            print(f"[gemini] unparseable JSON (try {i+1}/{attempts}): {e}; regenerating")
            time.sleep(3)
    raise RuntimeError(f"Gemini returned unparseable JSON after {attempts} tries: {last}")


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

    raw = _call_llm(config.BRAND_SYSTEM_PROMPT, user_prompt)
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
        return " ".join(text for _, text in parse_screenplay(out_dir))   # spoken words only
    with open(os.path.join(out_dir, "script.json")) as f:
        return json.load(f)["narration"]


def _to_str(prompt) -> str:
    """Normalise a scene prompt to a plain string regardless of what the LLM returned."""
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, dict):
        # Claude sometimes returns {"description": "...", "shot": "..."} etc.
        for key in ("description", "prompt", "shot", "scene", "text", "content"):
            if key in prompt and isinstance(prompt[key], str):
                return prompt[key]
        # fallback: join all string values
        return " ".join(str(v) for v in prompt.values() if v)
    return str(prompt)


def _inject_char_refs(scene_prompts: list, char_refs: dict) -> list[str]:
    """For every shot prompt, prepend the appearance+costume of any character whose
    name appears in it. This locks visual consistency across all parts."""
    result = []
    for raw in scene_prompts:
        prompt = _to_str(raw)
        injections = []
        prompt_upper = prompt.upper()
        for name_key, description in char_refs.items():
            first_name = name_key.split()[0]
            if first_name in prompt_upper or name_key in prompt_upper:
                injections.append(f"[{name_key}: {description}]")
        if injections:
            result.append(" ".join(injections) + " " + prompt)
        else:
            result.append(prompt)
    return result


def generate_part(spec: dict) -> dict:
    """Generate one 5–6 min serialized Part from a story spec (see src/story.py).
    Characters are described with locked appearance in every shot prompt for
    visual consistency across parts."""
    lo, hi = config.PART_WORDS
    part_n = spec.get("part", spec.get("episode", 1))  # support both keys
    total = spec.get("total", config.PARTS_PER_STORY)
    char_refs = spec.get("char_refs", {})

    chars_block = "\n".join(
        f"  - {c.get('name')} ({c.get('role')}): {c.get('appearance','')} Wearing: {c.get('costume','')}."
        for c in spec.get("characters", [])
    )
    recap = spec.get("recap") or "(this is Part 1 — no recap yet)"
    finale = ("This is the FINALE — bring the story to a satisfying, eerie, ambiguous resolution."
              if spec.get("is_finale") else "End on a strong cliffhanger that makes the viewer need Part {next_n}.".format(next_n=part_n+1))

    user_prompt = f"""Write Part {part_n} of {total} of the horror series "{spec['story_title']}".

LOGLINE: {spec.get('logline','')}
SETTING: {spec.get('setting','')}

LOCKED CHARACTERS (use these exact descriptions in shot prompts):
{chars_block}

STORY SO FAR: {recap}
WHAT THIS PART COVERS: {spec['beat']}
{finale}

This is a SHORT FILM screenplay. Characters SPEAK their own lines. Use "Narrator"
sparingly — only for brief scene-setting between dialogue beats.

Return ONLY a JSON object with these keys:

"lines": array of screenplay lines IN ORDER ({lo}–{hi} words of dialogue+narration total).
         Each: {{"speaker": "<character name or Narrator>", "text": "spoken line"}}.
         Grounded horror, NO gore. If part > 1, open with a brief Narrator recap line.
         End precisely on the beat above.

"scene_prompts": array of exactly {config.SCENES_PER_VIDEO} CINEMATIC SHOT descriptions IN STORY ORDER.
         Each shot MUST include ALL of the Hollywood 5 cinematography criteria:
           1. SHOT TYPE & FRAMING: establishing/medium/close-up, camera angle
           2. LIGHTING: dramatic motivated lighting — name the key light source and direction,
              deep shadows, soft rim light separating the subject from the background
           3. DEPTH: one out-of-focus foreground element, the subject tack-sharp in midground,
              atmospheric haze or detail in the background
           4. LEADING LINES: a specific environmental element (corridor, road, fence, beam of
              light) that pulls the eye toward the subject
           5. EMOTION & COLOUR: the exact mood/feeling of this beat + cinematic colour grade
              (teal-and-amber, desaturated, crushed blacks, etc.)
         Also: reference characters by NAME so the character injector can add their appearance.
         Landscape 16:9, photoreal, no on-screen text.

"youtube_title": "{spec['story_title']} — Part {part_n}: <hooky subtitle>" under 70 chars total

"youtube_description": 2–3 sentences with naturally woven search keywords (scary story,
         horror story, psychological horror, creepy, nosleep) + a subscribe CTA + series context
         ("Part {part_n} of {total}") + "original fiction" note

"hashtags": array of 10–12 tags without # — mix broad (horror, scarystories, creepy) and
         niche (nosleep, horrortok, storytime) tags plus the series slug

"tiktok_caption": under 150 chars, teases THIS part, ends on a curiosity hook

"thumbnail_text": 2–4 punchy uppercase words for the YouTube thumbnail card

"pinned_comment": one engagement-bait question about this part (drives comment replies)

"recap_for_next": 1–2 sentences summarising what happened this part (fed into next part's prompt)

"poster_prompt": one striking MOVIE-POSTER shot for the thumbnail — main character(s)
         facing the camera, intense horror expression, dramatic backlit silhouette or
         tight close-up, cinematic, landscape 16:9, photoreal, no on-screen text"""

    data = gen_json(config.BRAND_SYSTEM_PROMPT, user_prompt)

    lines = data.get("lines", [])
    data["narration"] = " ".join(l.get("text", "") for l in lines)
    data["voice_map"] = spec.get("voice_map", {})
    data["char_refs"] = char_refs

    # Inject character appearance into every scene prompt that mentions them
    raw_prompts = data.get("scene_prompts", [])
    data["scene_prompts"] = _inject_char_refs(raw_prompts, char_refs)
    data["scene_prompts_raw"] = raw_prompts   # keep uninjected for debugging

    sid = spec["story_id"]
    data["id"] = f"{sid}.{part_n}"
    data["title"] = data.get("youtube_title", f"{spec['story_title']} — Part {part_n}")
    slug = f"s{sid}p{part_n:02d}-{slugify(spec['story_title'])}"
    data["slug"] = slug

    out_dir = os.path.join(config.OUTPUT_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "script.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # narration.txt = editable screenplay (SPEAKER: line). Voice + captions read this.
    with open(os.path.join(out_dir, "narration.txt"), "w") as f:
        f.write("\n".join(f"{l.get('speaker','Narrator').upper()}: {l.get('text','')}" for l in lines))
    with open(os.path.join(out_dir, "script.txt"), "w") as f:
        f.write(f"{data['title']}\n\n")
        f.write("\n".join(f"{l.get('speaker','Narrator').upper()}: {l.get('text','')}" for l in lines))
        f.write("\n\n--- SHOTS ({n}) ---\n".format(n=len(data["scene_prompts"])))
        f.write("\n".join(f"{i+1}. {s}" for i, s in enumerate(data["scene_prompts"])))
    print(f"[script] {slug} ({len(data['narration'].split())} words, {len(lines)} lines, "
          f"{len(data['scene_prompts'])} shots)")
    return data


def generate_episode(spec: dict) -> dict:
    """Backward-compat alias → generate_part."""
    return generate_part(spec)


def parse_screenplay(out_dir: str):
    """Read narration.txt into [(speaker, text)] pairs. A row without 'SPEAKER:' is Narrator."""
    path = os.path.join(out_dir, "narration.txt")
    out = []
    with open(path) as f:
        for row in f.read().splitlines():
            row = row.strip()
            if not row:
                continue
            m = re.match(r"^([A-Z][A-Z0-9 ._'-]{0,28}):\s+(.*)$", row)
            out.append((m.group(1).strip(), m.group(2).strip()) if m else ("NARRATOR", row))
    return out


if __name__ == "__main__":
    from src import story
    generate_part(story.next_part_spec())
