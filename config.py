"""
Lights Out Tales — pipeline configuration ($0 stack).
Brand voice + generation settings live here so every part comes out consistent.

FREE TOOLS USED:
  - Script:   Claude API (Haiku — pennies/day)
  - Voice:    Microsoft Edge TTS (edge-tts, free, commercial-ok)
  - Visuals:  Pollinations.ai (free image generation, no API key)
  - Video:    Google Veo 3.1 via Gemini API (free tier, Google AI Studio key)
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

# ---------------------------------------------------------------- Script (LLM)
# Claude ONLY. Needs ANTHROPIC_API_KEY in .env / GitHub secret.
LLM_PROVIDER = "claude"
CLAUDE_ENDPOINT = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"   # cheapest model; bump to sonnet-4-6 / opus-4-8 for more quality
CLAUDE_MAX_TOKENS = 8192                      # enough for a 6-8 min screenplay + 22 scene prompts + metadata

# ---- Gemini — used ONLY for Veo video generation (free tier) ----
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
# Serialized story arcs: one 5-6 min PART per day. Story runs as many parts as it
# needs (PARTS_PER_STORY), then a brand-new story starts. Think Netflix series chapters.
PARTS_PER_STORY = 20           # each story = up to 20 parts (~1h 40m of content total)
EPISODES_PER_STORY = PARTS_PER_STORY   # backward-compat alias

# ~5-6 min parts. At ~140 wpm TTS + pauses this lands 5-6 min.
PART_WORDS = (900, 1150)
EPISODE_WORDS = PART_WORDS     # backward-compat alias

SHORTFORM_WORDS = (250, 350)   # standalone short-form queue entries (unchanged)
SHOTS_PER_PART = 18            # distinct cinematic shots per part
SCENES_PER_VIDEO = SHOTS_PER_PART  # alias used by generate_script.py

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
# Screenplay mode: each character is auto-assigned a distinct voice from these pools
# (kept consistent across episodes via the story bible). Narrator uses TTS_VOICE.
MALE_VOICES = ["en-US-EricNeural", "en-GB-RyanNeural", "en-US-BrianNeural",
               "en-AU-WilliamNeural", "en-US-DavisNeural", "en-US-RogerNeural"]
FEMALE_VOICES = ["en-US-AriaNeural", "en-US-JennyNeural", "en-GB-SoniaNeural",
                 "en-AU-NatashaNeural", "en-US-MichelleNeural", "en-US-AnaNeural"]

# ---------------------------------------------------------------- Visuals (Pollinations, FREE)
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
IMAGE_W, IMAGE_H = 1920, 1080  # 16:9 landscape — Netflix-movie framing for YouTube
# Style presets — pick one by name in ACTIVE_STYLE below. Compare them with:
#   python src/sample_styles.py
# The "photoreal" preset encodes the five cinematography principles (lighting, depth,
# composition/leading lines, emotion, colour grade) into every image + video prompt.
STYLES = {
    "photoreal": ("cinematic Hollywood film still, shot on 35mm anamorphic, dramatic "
                  "motivated lighting with deep shadows, soft key and rim light separating "
                  "the subject; shallow depth of field — a blurred out-of-focus element in the "
                  "foreground, the subject tack-sharp in the midground, atmospheric haze in the "
                  "background; strong leading lines guiding the eye to the subject; moody "
                  "cinematic colour grade (teal-and-amber, crushed blacks); volumetric light, "
                  "fine film grain, photoreal, hyper-detailed, no on-screen text"),
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

# ---------------------------------------------------------------- Video generation
# VIDEO_MODE sets the default renderer. Override per-run: VIDEO_PROVIDER=kling python ...
#
#  "stills"     FREE  Ken-Burns zoom (FFmpeg). No API key.
#  "kling"      PAID  ~$0.14/clip. Kling AI direct API. Key: KLING_API_KEY
#  "fal" / "ai" PAID  ~$0.05/clip. Kling via fal.ai.   Key: FAL_KEY
#  "replicate"  PAID  ~$0.02-0.06/clip. Wan/CogVideoX/LTX. Key: REPLICATE_API_TOKEN
#  "wan"               Shortcut for replicate + Wan2.1 model
#  "cogvideo"          Shortcut for replicate + CogVideoX model
#  "runpod"     PAID  ~$0.20/part on your serverless GPU. Key: RUNPOD_API_KEY
#  "veo"        PAID  Google Veo 2 (requires GCP billing)
VIDEO_MODE = "stills"   # Ken-Burns zoom — free, no API needed.

# ---- Google Veo 3.1 (FREE — needs GEMINI_API_KEY from aistudio.google.com/apikey) ----
VEO_MODEL = "veo-2.0-generate-001"   # publicly available on AI Studio free tier
VEO_CLIP_SECONDS = 8                     # max clip length on free tier
# Motion prompt appended to every shot: cinematic but subtle so character stays consistent
VEO_MOTION = ("slow cinematic camera push-in, eerie horror atmosphere, "
              "realistic motion, characters stay visually consistent, "
              "no warping, no morphing, no on-screen text, "
              "subtle environmental movement — breath, shadow, leaves")

# ---- RunPod serverless (open-source video on a rented GPU) — see cloud/RUNPOD_SETUP.md
RUNPOD_BASE = "https://api.runpod.ai/v2"
RUNPOD_ENDPOINT_ID = ""              # your serverless endpoint id (set after deploying)
RUNPOD_MODE = "comfyui"
RUNPOD_WORKFLOW = "comfyui_workflows/ltx_i2v.json"
RUNPOD_NODE_PROMPT = "positive"
RUNPOD_FRAMES = 97                   # LTX ~24fps; 97 frames ≈ 4s

# ---- Kling direct API (PAID ~$0.14/clip std, ~$0.28/clip pro) ----
KLING_MODEL = "kling-v1-5"          # kling-v1 | kling-v1-5 | kling-v2
KLING_MODE  = "std"                  # std | pro

# ---- fal.ai Kling (PAID ~$0.05/clip) ----
FAL_QUEUE_BASE = "https://queue.fal.run"
FAL_MODEL = "fal-ai/kling-video/v1/standard/image-to-video"
AI_CLIP_SECONDS = 5
AI_MOTION = ("subtle cinematic camera motion, slow push-in, eerie horror atmosphere, "
             "realistic, keep the character consistent, no warping, no morphing, no text")

# ---- Replicate open-source models (PAID ~$0.02-0.06/clip) ----
REPLICATE_MODEL = "wan"   # wan | cogvideo | ltx | stable | hunyuan

# ---- Lip-sync hybrid renderer (RECOMMENDED for talking-character channels) ----
# VIDEO_MODE = "lipsync" enables this renderer.
# Dialogue shots (CU/MCU/OTS) → lip-sync model below
# Wide shots (ES/WS/LOW/HIGH) → Wan2.1 motion
# Insert shots (INS/SIL/REFL) → Ken-Burns (free)
# All powered by Replicate — one REPLICATE_API_TOKEN covers everything.
LIPSYNC_MODEL = "sadtalker"  # sadtalker | latentsync | wav2lip
#   sadtalker  — reliable, good quality, ~$0.01/clip
#   latentsync — sharper lip movement, ~$0.02/clip (recommended upgrade)
#   wav2lip    — fastest, classic, ~$0.01/clip

# ---- Cinematic render look (free, core ffmpeg filters) ----
CROSSFADE = 0.5                       # seconds of crossfade dissolve between scenes
# subtle contrast + slight desaturation + vignette + fine film grain:
FILM_GRADE = "eq=contrast=1.06:saturation=0.92,vignette=PI/5,noise=alls=8:allf=t"

# ---------------------------------------------------------------- TikTok clipping
TIKTOK_CLIPS_PER_VIDEO = 3
CLIP_SECONDS = 50            # length of each promo teaser clip cut from the long episode
TIKTOK_DAYPARTS = ["07:00", "12:00", "16:00"]   # 7am / 12pm / 4pm (local)
CLIP_RATIO = "9:16"
CLIP_CTA = "Full episode on YouTube — @thelightsouttales"
CLIP_LABELS = ["PART 1", "PART 2", "PART 3"]
CLIP_OVERLAP_SEC = 1.0

# ---------------------------------------------------------------- Paths / status
QUEUE_FILE = "content_queue.csv"
OUTPUT_DIR = "outputs"
# queued -> script_ready -> [approve] -> rendered -> [approve] -> uploaded -> clipped -> posted
STATUS_FLOW = ["queued", "script_ready", "rendered", "uploaded", "clipped", "posted", "skipped"]
