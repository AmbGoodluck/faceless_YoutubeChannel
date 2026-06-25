# Amadu Studios — Video Renderer Setup Guide

Every renderer uses **Pollinations.ai for images** (completely free, no key needed).
Only the *video* step differs. Start free, upgrade when you're ready.

---

## Renderer Comparison

| Renderer | Characters Talk? | Video Quality | Cost/Part | Speed | API Key |
|---|---|---|---|---|---|
| `stills` | ✗ zoom only | ★ | **Free** | Instant | None |
| `lipsync` | ✓ **lip-synced** | ★★★★★ | ~$0.50–0.80 | 10–18 min | REPLICATE_API_TOKEN |
| `replicate` (Wan2.1) | ✗ motion only | ★★★★ | ~$0.40–0.80 | 8–12 min | REPLICATE_API_TOKEN |
| `replicate` (CogVideoX) | ✗ motion only | ★★★★ | ~$0.50–1.00 | 10–15 min | REPLICATE_API_TOKEN |
| `replicate` (LTX) | ✗ motion only | ★★★ | ~$0.20–0.40 | 4–6 min | REPLICATE_API_TOKEN |
| `fal` (Kling via fal.ai) | ✗ motion only | ★★★★ | ~$0.90–1.80 | 8–12 min | FAL_KEY |
| `kling` (direct API) | ✗ motion only | ★★★★ | ~$2.50–3.20 | 8–12 min | KLING_API_KEY |
| `runpod` (your GPU) | ✗ motion only | ★★★★ | ~$0.20–0.40 | 6–10 min | RUNPOD_API_KEY + Endpoint ID |

**Recommendation: use `lipsync` mode.** Characters actually move their mouths in sync with the
voice. Close-up shots are lip-synced, wide shots have real environmental motion. One Replicate
token covers everything. ~$0.50–0.80/part.

---

## Option 0: lipsync (RECOMMENDED — ~$0.50–0.80/part, characters actually talk)

This is the mode designed for this channel. Characters lip-sync to their dialogue in
close-up shots. Wide/establishing shots have real environmental motion. All on one
Replicate API token.

### How it routes each shot automatically

| Shot type | Renderer | Cost |
|---|---|---|
| CU, MCU, OTS, RXN, TWO (face visible) | SadTalker/LatentSync — lip sync | ~$0.01–0.02 |
| ES, WS, LOW, HIGH, BIRD (wide angle) | Wan2.1 — environmental motion | ~$0.03–0.04 |
| INS, SIL, REFL (no face) | Ken-Burns zoom | Free |

### Steps

1. Sign up at **replicate.com**
2. **replicate.com/account/api-tokens** → Create Token
3. Add to `.env`:
   ```
   REPLICATE_API_TOKEN=r8_xxxxxxxxxxxxxxxxxx
   ```
4. Install the Replicate client:
   ```bash
   pip install replicate --break-system-packages
   ```
5. In `config.py`:
   ```python
   VIDEO_MODE    = "lipsync"
   LIPSYNC_MODEL = "sadtalker"   # or "latentsync" for sharper lip movement
   ```

### Run

```bash
set -a; source .env; set +a
python amadu_studios/run.py --part 1

# Or override per-run without changing config:
VIDEO_PROVIDER=lipsync python amadu_studios/run.py --part 1

# Use LatentSync (better quality, slightly slower):
VIDEO_PROVIDER=lipsync LIPSYNC_MODEL=latentsync python amadu_studios/run.py --part 1
```

### Lip-sync model comparison

| Model | Quality | Speed | Cost/clip |
|---|---|---|---|
| `sadtalker` | Good, natural head movement | ~2 min | ~$0.01 |
| `latentsync` | Sharper lips, more accurate | ~3 min | ~$0.02 |
| `wav2lip` | Classic, fastest | ~1 min | ~$0.01 |

Start with `sadtalker`. Upgrade to `latentsync` when you want tighter sync.

---

## Option 1: stills (Free — default)

No setup needed. Pure Ken-Burns zoom via FFmpeg.

```bash
# Already the default. No changes needed.
python amadu_studios/run.py --part 1
```

---

## Option 2: Replicate — Wan2.1 (Recommended paid upgrade, ~$0.02/clip)

Wan2.1 is Alibaba's open-source image-to-video model. Excellent motion coherence.

### Steps

1. Create account at **replicate.com**
2. Go to **replicate.com/account/api-tokens** → Create Token
3. Add to `.env`:
   ```
   REPLICATE_API_TOKEN=r8_xxxxxxxxxxxxxxxxxx
   ```
4. In `config.py`, set:
   ```python
   VIDEO_MODE = "replicate"
   REPLICATE_MODEL = "wan"    # or: cogvideo | ltx | hunyuan
   ```

### Run

```bash
# Default model (wan)
python amadu_studios/run.py --part 1

# Override model per-run
REPLICATE_MODEL=cogvideo python amadu_studios/run.py --part 1

# Override renderer per-run without changing config
VIDEO_PROVIDER=replicate REPLICATE_MODEL=ltx python amadu_studios/run.py --part 1
```

### Available Replicate models

| Model key | Replicate slug | Notes |
|---|---|---|
| `wan` | wavespeed-ai/wan-2.1-i2v-480p | Best motion, cheap |
| `cogvideo` | zsxkib/cogvideox-5b | Great quality, medium cost |
| `ltx` | lightricks/ltx-video | Fastest, good for testing |
| `hunyuan` | tencent/hunyuan-video | SOTA quality, slow |
| `stable` | stability-ai/stable-video-diffusion | Classic SVD, image-only |

---

## Option 3: fal.ai — Kling via fal (~$0.05/clip)

### Steps

1. Create account at **fal.ai**
2. Go to **fal.ai/dashboard/keys** → Create Key
3. Add to `.env`:
   ```
   FAL_KEY=your_fal_key_here
   ```
4. In `config.py`:
   ```python
   VIDEO_MODE = "fal"
   ```

### Run

```bash
python amadu_studios/run.py --part 1
# or per-run:
VIDEO_PROVIDER=fal python amadu_studios/run.py --part 1
```

---

## Option 4: Kling Direct API (~$0.14/clip standard)

Best quality if you want full control without a middleman.

### Steps

1. Sign up at **platform.klingai.com**
2. Go to **Settings > API Keys** → Create Key
3. Add to `.env`:
   ```
   KLING_API_KEY=your_kling_key_here
   ```
4. In `config.py`:
   ```python
   VIDEO_MODE = "kling"
   KLING_MODEL = "kling-v1-5"   # kling-v1 | kling-v1-5 | kling-v2
   KLING_MODE  = "std"           # std | pro
   ```

### Run

```bash
python amadu_studios/run.py --part 1
# or per-run:
VIDEO_PROVIDER=kling python amadu_studios/run.py --part 1
```

---

## Option 5: RunPod — Your Own GPU (~$0.20–0.40/part, cheapest real video)

Best long-term cost for high volume. You deploy a serverless GPU endpoint once.

### Steps

1. Sign up at **runpod.io**
2. Go to **Serverless > + New Endpoint**
3. Choose a template:
   - Search for **"Wan 2.1 I2V"** (recommended) — click Deploy
   - Or use **worker-comfyui** for full ComfyUI control
4. Select GPU: **A40** (best value) or **RTX 4090**
5. Set Min Workers = 0 (scale to zero when idle)
6. Copy the **Endpoint ID** from the dashboard (looks like `abc123xyz456`)
7. Go to **Settings > API Keys** → Create key
8. Add to `.env`:
   ```
   RUNPOD_API_KEY=your_key_here
   RUNPOD_ENDPOINT_ID=abc123xyz456
   ```
9. In `config.py`:
   ```python
   VIDEO_MODE       = "runpod"
   RUNPOD_MODE      = "simple"     # "simple" for pre-built; "comfyui" for custom
   RUNPOD_FRAMES    = 81           # 81 frames @ 16fps ≈ 5s (adjust for your model)
   ```

#### For ComfyUI mode only:
10. Export your workflow from ComfyUI as **Save (API Format)**
11. Save it to `comfyui_workflows/wan_i2v.json`
12. Set `RUNPOD_MODE = "comfyui"` in config

### Run

```bash
python amadu_studios/run.py --part 1
# or per-run:
VIDEO_PROVIDER=runpod python amadu_studios/run.py --part 1
```

---

## Switching renderers without touching config

Use the `VIDEO_PROVIDER` environment variable to override `VIDEO_MODE` for a single run:

```bash
VIDEO_PROVIDER=kling python amadu_studios/run.py --part 1
VIDEO_PROVIDER=replicate REPLICATE_MODEL=wan python amadu_studios/run.py --part 1
VIDEO_PROVIDER=runpod python amadu_studios/run.py --part 1
VIDEO_PROVIDER=stills python amadu_studios/run.py --part 1
```

---

## .env template

```env
# Required
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxx

# Optional — only needed for your chosen video renderer
REPLICATE_API_TOKEN=r8_xxxxxxxxxx   # replicate
FAL_KEY=xxxxxxxx                     # fal
KLING_API_KEY=xxxxxxxxxx             # kling
RUNPOD_API_KEY=xxxxxxxxxx            # runpod
RUNPOD_ENDPOINT_ID=abc123xyz456      # runpod

# Optional Gemini (for future Veo upgrade)
GEMINI_API_KEY=AIzaxxxxxxxx

# YouTube upload
# OAuth is handled by client_secret.json — see cloud/YOUTUBE_SETUP.md
```

---

## Cost Estimator

For a 20-part series, one new part per day. 16 shots/part assumed.

| Renderer | Characters Talk? | Cost/Part | Monthly (30 parts) |
|---|---|---|---|
| stills | ✗ | $0 | $0 |
| **lipsync/sadtalker** | **✓** | **~$0.55** | **~$16** |
| lipsync/latentsync | ✓ | ~$0.75 | ~$22 |
| Replicate/Wan | ✗ | ~$0.60 | ~$18 |
| Replicate/LTX | ✗ | ~$0.30 | ~$9 |
| fal/Kling | ✗ | ~$1.35 | ~$40 |
| Kling direct | ✗ | ~$2.80 | ~$84 |
| RunPod (own GPU) | ✗ | ~$0.30 | ~$9 |

LLM (Claude Haiku) adds ~$0.02/part. Voice (Edge TTS) is free.

**Best choice for this channel: `lipsync` mode at ~$16/month.** You get talking characters,
real motion in wide shots, and it runs automatically every day via `--auto`.
