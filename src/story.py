"""
Serialized-story manager. Tracks which story + episode we're on, generates a new
10-episode story "bible" when one finishes, and hands the next episode's spec to the
script generator. State persists in story_state.json (committed by the cloud workflow).

Flow: episode 1..10 of a story (continuity + cliffhangers), episode 10 resolves it,
then the next run starts a brand-new story.
"""
from __future__ import annotations
import os, sys, json, re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import generate_script   # reuse _call_gemini + _extract_json

STATE = "story_state.json"

BIBLE_SYSTEM = """\
You are the show-runner for a faceless YouTube horror series for a TEEN (13+) audience.
You invent original, serialized horror stories — grounded, eerie, psychological, NO gore,
advertiser-safe. Stories can follow kids/teens experiencing something they can't explain,
or any horror premise. Each story runs exactly 10 episodes with a clear arc that builds
tension and resolves in episode 10.
"""


def _load():
    return json.load(open(STATE)) if os.path.exists(STATE) else None


def _save(st):
    json.dump(st, open(STATE, "w"), indent=2, ensure_ascii=False)


def _gen_bible() -> dict:
    n = config.EPISODES_PER_STORY
    prompt = f"""Invent a NEW original {n}-episode teen horror story. Return ONLY JSON:
{{
  "story_title": "short, hooky series title",
  "logline": "one sentence describing the whole story",
  "setting": "where/when it takes place",
  "characters": [ {{"name": "...", "role": "..."}} (2-4 main characters) ],
  "episodes": [ {n} objects: {{"n": 1.., "beat": "what happens this episode, advancing the arc;
                episode {n} must resolve the story"}} ]
}}"""
    raw = generate_script._call_gemini(BIBLE_SYSTEM, prompt)
    bible = json.loads(generate_script._extract_json(raw))
    return bible


def next_episode_spec() -> dict:
    """Return the spec for the NEXT episode. Does NOT advance the counter — call
    commit() only after the episode is successfully generated, so failed runs don't
    skip episodes. The story bible IS persisted immediately (so retries reuse it)."""
    st = _load()
    if not st or st.get("episode", 0) >= config.EPISODES_PER_STORY:
        story_id = (st.get("story_id", 0) + 1) if st else 1
        bible = _gen_bible()
        st = {"story_id": story_id, "episode": 0, "bible": bible, "last_recap": ""}
        _save(st)
        print(f"[story] new story #{story_id}: {bible.get('story_title')}")

    n = st["episode"] + 1                  # the episode we're about to make
    bible = st["bible"]
    beats = bible.get("episodes", [])
    beat = beats[n - 1]["beat"] if n - 1 < len(beats) else "continue the story"

    return {
        "story_id": st["story_id"], "episode": n, "total": config.EPISODES_PER_STORY,
        "story_title": bible.get("story_title", "Untitled"),
        "logline": bible.get("logline", ""),
        "setting": bible.get("setting", ""),
        "characters": bible.get("characters", []),
        "beat": beat, "recap": st.get("last_recap", ""),
        "is_finale": n == config.EPISODES_PER_STORY,
    }


def commit(recap: str):
    """Mark the current episode as done (advance the counter) + store its recap."""
    st = _load()
    if st:
        st["episode"] += 1
        st["last_recap"] = recap or ""
        _save(st)


# backwards-compatible alias
def save_recap(recap: str):
    commit(recap)


if __name__ == "__main__":
    print(json.dumps(next_episode_spec(), indent=2))
