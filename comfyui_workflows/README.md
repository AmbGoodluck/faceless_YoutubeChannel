# ComfyUI workflows

Put your exported **LTX image-to-video** workflow here as `ltx_i2v.json`.

How to get it:
1. In ComfyUI, build an LTX-Video image-to-video graph (LoadImage → LTX nodes → VHS video output).
2. Settings → enable "Enable Dev mode Options".
3. Click **Save (API Format)** → save the file as `ltx_i2v.json` in this folder.

`src/generate_runpod_video.py` (RUNPOD_MODE="comfyui") loads this JSON and, per scene,
injects the scene image into the `LoadImage` node and the prompt into the positive
`CLIPTextEncode` node, then sends it to your RunPod worker-comfyui endpoint.

(If you use a ready-made endpoint instead — RUNPOD_MODE="simple" — you don't need this file.)
