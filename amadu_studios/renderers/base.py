"""
Amadu Studios — Renderer Interface + Factory
Abstract base class. Every renderer implements render_image() and optionally render_video().
Swapping renderers never touches any upstream agent.

Supported renderers (VIDEO_MODE / VIDEO_PROVIDER):
  stills / pollinations — Free. Pollinations images + Ken-Burns zoom (FFmpeg). No API key.
  kling                 — Paid ~$0.14/clip. Direct Kling AI API. Key: KLING_API_KEY
  fal                   — Paid ~$0.05/clip. Kling via fal.ai middleman. Key: FAL_KEY
  replicate             — Paid ~$0.02-0.06/clip. Open-source models (Wan/CogVideoX/LTX/HunyuanVideo).
                          Key: REPLICATE_API_TOKEN. Model: REPLICATE_MODEL=wan|cogvideo|ltx|hunyuan
  runpod                — Paid ~$0.20/part. Your own serverless GPU. Key: RUNPOD_API_KEY +
                          RUNPOD_ENDPOINT_ID. Mode: RUNPOD_MODE=simple|comfyui

Selection priority (first match wins):
  1. VIDEO_PROVIDER env var  (overrides everything, useful per-run)
  2. config.VIDEO_MODE
  3. "stills" fallback

All paid renderers use Pollinations for images (free) and their API only for video.
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class BaseRenderer(ABC):
    name: str = "base"

    @abstractmethod
    def render_image(self, shot_id: int, prompt: str, out_dir: str,
                     width: int = 1920, height: int = 1080,
                     seed: int = None) -> str:
        """
        Render a still image. Returns absolute path to saved file.
        seed: optional visual seed for consistency (Pollinations uses it;
              other renderers may ignore it).
        """
        ...

    def render_video(self, shot_id: int, image_path: str, prompt: str,
                     out_dir: str, seconds: int = 6) -> str:
        """Animate an image into a video clip. Returns path or '' if unsupported."""
        return ""

    @property
    def supports_video(self) -> bool:
        return False


# ── Factory ───────────────────────────────────────────────────────────────────

_RENDERER_MAP = {
    # mode string → (module_path, class_name)
    "stills":       ("amadu_studios.renderers.pollinations", "PollinationsRenderer"),
    "pollinations": ("amadu_studios.renderers.pollinations", "PollinationsRenderer"),
    "kling":        ("amadu_studios.renderers.kling",        "KlingRenderer"),
    "fal":          ("amadu_studios.renderers.fal",          "FalRenderer"),
    "ai":           ("amadu_studios.renderers.fal",          "FalRenderer"),   # legacy alias
    "replicate":    ("amadu_studios.renderers.replicate",    "ReplicateRenderer"),
    "wan":          ("amadu_studios.renderers.replicate",    "ReplicateRenderer"),  # shortcut
    "cogvideo":     ("amadu_studios.renderers.replicate",    "ReplicateRenderer"),  # shortcut
    "runpod":       ("amadu_studios.renderers.runpod",       "RunPodRenderer"),
    # ── Lip-sync hybrid (RECOMMENDED for talking-character channels) ──────────
    "lipsync":      ("amadu_studios.renderers.lipsync",      "LipSyncRenderer"),
    "sadtalker":    ("amadu_studios.renderers.lipsync",      "LipSyncRenderer"),   # shortcut
    "latentsync":   ("amadu_studios.renderers.lipsync",      "LipSyncRenderer"),   # shortcut
}


def get_renderer(mode: str = None) -> BaseRenderer:
    """
    Renderer factory.
    mode arg overrides config. Falls back to "stills" (free) if unknown.
    """
    import os, importlib
    import config

    # Priority: explicit arg > env var > config
    selected = (
        mode
        or os.environ.get("VIDEO_PROVIDER")
        or getattr(config, "VIDEO_MODE", "stills")
        or "stills"
    ).lower()

    entry = _RENDERER_MAP.get(selected)
    if not entry:
        print(f"[renderer] unknown mode '{selected}', falling back to 'stills'")
        entry = _RENDERER_MAP["stills"]

    module_path, class_name = entry

    # For Replicate shortcut aliases, pass the model key
    if selected in ("wan", "cogvideo"):
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls(model_key=selected)

    # For lip-sync model shortcuts, pass the lipsync_model key
    if selected in ("sadtalker", "latentsync"):
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls(lipsync_model=selected)

    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()


def list_renderers() -> list[str]:
    """Return all supported renderer mode strings."""
    return sorted(set(_RENDERER_MAP.keys()))
