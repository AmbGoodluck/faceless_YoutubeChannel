# RunPod video setup — open-source AI video on a rented GPU

Goal: animate each scene image into a real video clip with an open-source model
(LTX-Video / Wan) on a **RunPod Serverless** endpoint. It **scales to zero** — you pay
only for the seconds each job runs (~$0.22/hr GPU), so a 6–8 min episode costs roughly
**$0.50–1.50** instead of hundreds of credits.

You only flip `config.VIDEO_MODE = "runpod"` once this is deployed. Until then the
pipeline stays on free `stills`.

## Pick one of two deploy paths

### Path A — Easiest: a ready-made endpoint (no Docker)
RunPod hosts public serverless endpoints (e.g. **WAN 2.2 Image-to-Video**).
1. https://www.runpod.io → **Serverless** → find the WAN 2.2 I2V endpoint (or deploy it from the hub).
2. Copy its **Endpoint ID**.
3. In `config.py`: set `RUNPOD_MODE = "simple"` and `RUNPOD_ENDPOINT_ID = "<id>"`.
4. Check the endpoint's input schema on its page; if it doesn't use `image`/`prompt`,
   tell me the field names and I'll match them in `generate_runpod_video.py`.

### Path B — Cheapest/most control: your own worker-comfyui + LTX
1. Deploy **`runpod-workers/worker-comfyui`** as a Serverless endpoint
   (RunPod → Serverless → New Endpoint → from the worker-comfyui image), GPU = RTX 3090/4090.
   In **Configure ComfyUI**, enable **Refresh Worker** (this is what scales to zero).
2. Make sure the LTX-Video model + the ComfyUI-LTXVideo nodes are in the image/volume.
3. In ComfyUI locally, build an **LTX image-to-video** workflow, then **Save (API Format)**.
   Put that JSON at `comfyui_workflows/ltx_i2v.json` in the repo.
4. In `config.py`: `RUNPOD_MODE = "comfyui"`, `RUNPOD_ENDPOINT_ID = "<id>"`,
   `RUNPOD_WORKFLOW = "comfyui_workflows/ltx_i2v.json"`.
   The client injects the scene image (as the `LoadImage` node) and the prompt (into the
   positive `CLIPTextEncode`) automatically.

## API key + secrets
1. https://www.runpod.io/console/user/settings → **API Keys** → create one.
2. Local: add `RUNPOD_API_KEY=...` to `.env`.
3. Cloud: add `RUNPOD_API_KEY` as a GitHub repo secret (the workflow already passes it).

## Turn it on + test
```
# config.py: VIDEO_MODE = "runpod"
set -a; source .env; set +a
python cloud/run_stage.py render --episode s1e01-the-glitch-in-the-grain
```
You'll see `[runpod] scene 1 → ...mp4` as each clip renders on your GPU endpoint, then
the pipeline stitches them + your multi-voice dialogue + captions into the episode.

## Costs
- GPU: ~$0.22/hr (3090) / ~$0.39/hr (4090), billed per second, scale-to-zero when idle.
- Each LTX clip ≈ seconds of GPU → roughly **$0.50–1.50 per full episode**.
- Everything else (script, Flux images via Pollinations, voices, assembly) stays free.

> Output parsing: worker-comfyui returns the clip as base64 or a URL; the client handles
> both common shapes. If your endpoint returns a different structure, paste one job's
> `output` JSON and I'll adjust `_extract_video()`.
