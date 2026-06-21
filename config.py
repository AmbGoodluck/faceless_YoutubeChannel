"""
Lights Out Tales — pipeline configuration ($0 stack).
Brand voice + generation settings live here so every episode comes out consistent.

FREE TOOLS USED:
  - Script:   Google Gemini API (free tier, no credit card)
  - Voice:    Microsoft Edge TTS (edge-tts, free, commercial-ok)
  - Visuals:  Pollinations.ai (free image generation, no API key)
  - Assembly: FFmpeg (free)
  - Upload:   YouTube Data API (free quota)
  - Schedule: GitHub Actions (free tier)
"""

# ---------------------------------------------------------------- Channel brand
CHANNEL_NAME = "Lights Out Tales"
HANDLE = "@thelightsouttales"
ACCENT_HEX = "#C8932B"  # amber — locked

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

# ---------------------------------------------------------------- Script (Gemini, FREE)
# Free key from https://aistudio.google.com/apikey  (no credit card)
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
SHORTFORM_WORDS = (130, 170)   # ~30-60s of narration
SCENES_PER_VIDEO = 6           # distinct visual beats

# ---------------------------------------------------------------- Voice (Edge TTS, FREE)
# List voices with:  edge-tts --list-voices | grep en-
TTS_VOICE = "en-US-ChristopherNeural"  # deep, mature narrator (less overused than Guy)
TTS_RATE = "-8%"               # slightly slower = more dread
TTS_PITCH = "-2Hz"
# Candidates to audition with: python src/sample_voices.py
VOICE_CANDIDATES = [
    "en-US-ChristopherNeural", "en-US-EricNeural", "en-GB-RyanNeural",
    "en-US-RogerNeural", "en-AU-WilliamNeural", "en-US-BrianNeural",
]

# ---------------------------------------------------------------- Visuals (Pollinations, FREE)
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
IMAGE_W, IMAGE_H = 1080, 1920  # vertical
# Style presets — pick one by name in ACTIVE_STYLE below. Compare them with:
#   python src/sample_styles.py
STYLES = {
    "photoreal": ("dark cinematic, moody low-key lighting, film grain, desaturated, "
                  "amber practical light, realistic people with natural detailed faces, "
                  "cinematic portrait depth, photorealistic, 4k, no on-screen text"),
    "ink_sketch": ("eerie pen and ink illustration, heavy cross-hatching, vintage "
                   "engraving, storybook horror, monochrome with a single amber accent, "
                   "no faces, no text"),
    "painterly": ("moody digital painting, atmospheric concept art, dramatic chiaroscuro, "
                  "muted palette with amber light, brush texture, no faces, no text"),
    "cartoon": ("stylized 2d cartoon illustration, bold clean shapes, cel shaded, "
                "moody night palette, amber light, slight horror mood, no faces, no text"),
}
ACTIVE_STYLE = "photoreal"          # <-- change to switch the whole channel's look
VISUAL_STYLE = STYLES[ACTIVE_STYLE]

# ---------------------------------------------------------------- AI video (fal.ai, PAID)
# "ai"     = animate each scene image into a real video clip (image-to-video, costs money)
# "stills" = free Ken-Burns zoom on the images (no cost)
VIDEO_MODE = "ai"
FAL_QUEUE_BASE = "https://queue.fal.run"
# Pick/confirm a model + its input fields at https://fal.ai/explore/image-to-video-apis
# Cheaper: fal-ai/ltx-video  | balanced: fal-ai/kling-video/v1/standard/image-to-video
# top end: fal-ai/veo2/image-to-video
FAL_MODEL = "fal-ai/kling-video/v1/standard/image-to-video"
AI_CLIP_SECONDS = 5
AI_MOTION = ("subtle cinematic camera motion, slow push-in, eerie horror atmosphere, "
             "realistic, keep the character consistent, no warping, no morphing, no text")

# ---------------------------------------------------------------- TikTok clipping
TIKTOK_CLIPS_PER_VIDEO = 3
TIKTOK_DAYPARTS = ["07:00", "12:00", "16:00"]   # 7am / 12pm / 4pm (local)
CLIP_RATIO = "9:16"
CLIP_CTA = "Full story on YouTube — @thelightsouttales"
CLIP_LABELS = ["PART 1", "PART 2", "PART 3"]
CLIP_OVERLAP_SEC = 1.0

# ---------------------------------------------------------------- Paths / status
QUEUE_FILE = "content_queue.csv"
OUTPUT_DIR = "outputs"
# queued -> script_ready -> [approve] -> rendered -> [approve] -> uploaded -> clipped -> posted
STATUS_FLOW = ["queued", "script_ready", "rendered", "uploaded", "clipped", "posted", "skipped"]
