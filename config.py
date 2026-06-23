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
# Serialized story arcs: one 6-8 min episode per day, 10 episodes per story,
# then a brand-new story starts the next day.
EPISODES_PER_STORY = 10
EPISODE_WORDS = (260, 420)     # ~1.5-2.5 min premium episodes (Gen-Z attention + cost)
SCENES_PER_VIDEO = 14          # distinct cinematic shots across the episode

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

# ---------------------------------------------------------------- AI video (fal.ai, PAID)
# "stills"  = free Ken-Burns zoom on the images (no cost) — current default
# "runpod"  = open-source LTX/Wan image-to-video on your RunPod serverless GPU (cheap, ~$1/episode)
# "ai"      = fal.ai image-to-video (managed, PAID per clip)
VIDEO_MODE = "stills"

# ---- RunPod serverless (open-source video on a rented GPU) — see cloud/RUNPOD_SETUP.md
RUNPOD_BASE = "https://api.runpod.ai/v2"
RUNPOD_ENDPOINT_ID = ""              # your serverless endpoint id (set after deploying)
RUNPOD_MODE = "comfyui"              # "comfyui" (worker-comfyui + workflow) or "simple" (ready endpoint)
RUNPOD_WORKFLOW = "comfyui_workflows/ltx_i2v.json"   # export from ComfyUI: Save (API Format)
RUNPOD_NODE_PROMPT = "positive"      # title hint for the positive CLIPTextEncode node
RUNPOD_FRAMES = 97                   # LTX ~24fps; 97 frames ≈ 4s

# ---- Cinematic render look (free, core ffmpeg filters) ----
CROSSFADE = 0.5                       # seconds of crossfade dissolve between scenes
# subtle contrast + slight desaturation + vignette + fine film grain:
FILM_GRADE = "eq=contrast=1.06:saturation=0.92,vignette=PI/5,noise=alls=8:allf=t"
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
