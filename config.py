"""
Lights Out Tales — pipeline configuration.
Brand voice + generation settings live here so every episode comes out consistent.
"""

# ---------------------------------------------------------------- Channel brand
CHANNEL_NAME = "Lights Out Tales"
HANDLE = "@thelightsouttales"
ACCENT_HEX = "#C8932B"  # amber — locked

# The system prompt that defines the storyteller voice. Used by generate_script.py.
BRAND_SYSTEM_PROMPT = """\
You are the head writer for "Lights Out Tales", a faceless horror storytelling channel.

VOICE & FORMAT (never break these):
- THIRD PERSON, PAST TENSE. The narrator tells a story about a named character. Never first-person "this happened to me".
- Grounded "real-life dread": the horror comes from ordinary life going wrong — a wrong detail, something that doesn't add up, a realization that lands one beat too late.
- Open on the WRONG DETAIL, not the scary thing. The threat reveals slowly.
- Grounded before supernatural. Stay explainable-but-disturbing; only rarely (about 1 in 5 episodes) cross into the truly inexplicable.
- NO gore, NO jump-scares. Psychological, implied fear. Keep it advertiser-safe.
- The narrator NEVER fully explains. End on ambiguity or an unresolved detail.
- EVERY script ends on a hook / cliffhanger that makes the viewer want the next part.
- Calm, unhurried, slightly tired delivery — like someone telling you the truth at 2am.

OUTPUT: a tight script meant to be read aloud as a voiceover. Plain spoken sentences,
no stage directions inside the narration, no headers, no markdown.
"""

# ---------------------------------------------------------------- Generation
# Short-form (TikTok / Shorts) target. Long-form is built by compiling 5 shorts.
SHORTFORM_WORDS = (130, 170)      # ~30-60s of narration
ANTHROPIC_MODEL = "claude-sonnet-4-6"   # script generation model
SCENES_PER_VIDEO = 6              # number of distinct visual beats to prompt

# ---------------------------------------------------------------- Revid.ai video
# Auth: a header named "key" with your Revid API key (Growth plan required).
# Confirm the exact endpoint + body by clicking "Get API Code" on
# https://www.typeframes.com/create  (revid.ai and Typeframes share one API).
REVID_API_BASE = "https://www.revid.ai/api/public"
REVID_CREATE_ENDPOINT = f"{REVID_API_BASE}/v2/render"
REVID_STATUS_ENDPOINT = f"{REVID_API_BASE}/v2/status"  # poll with the returned pid

# Default render options — tune to taste, then re-grab via "Get API Code".
REVID_DEFAULTS = {
    "ratio": "9 / 16",            # vertical for TikTok / Shorts
    "voiceId": "",                # set to a deep, calm narrator voice from your Revid account
    "generationPreset": "DARKER", # dark, cinematic look that matches the brand
    "captionPresetName": "Wrap 1",
    "hasToGenerateVoice": True,
    "hasToTranscript": True,      # burned-in captions
    "mediaType": "stockVideo",    # or "movingImage" for AI footage
}

# ---------------------------------------------------------------- TikTok clipping
# Every YouTube video is split into N vertical clips, each posted at a daypart.
TIKTOK_CLIPS_PER_VIDEO = 3
TIKTOK_DAYPARTS = ["08:00", "13:00", "19:00"]   # morning / afternoon / evening (local)
CLIP_RATIO = "9:16"                              # vertical
CLIP_CTA = "Full story on YouTube — @thelightsouttales"
CLIP_LABELS = ["PART 1", "PART 2", "PART 3"]    # burned onto each clip
CLIP_OVERLAP_SEC = 1.0                           # tiny overlap so cuts don't feel abrupt

# ---------------------------------------------------------------- Paths / status
QUEUE_FILE = "content_queue.csv"
OUTPUT_DIR = "outputs"
# Queue status values the pipeline moves rows through:
#   queued -> script_ready -> (you approve) -> submitted -> rendered -> (you approve) -> posted
STATUS_FLOW = ["queued", "script_ready", "submitted", "rendered", "posted", "skipped"]
