"""
Stage 3b — Scene images via Pollinations.ai (FREE, no API key).
One image per scene prompt, in the channel's dark cinematic style.

Produces: <out_dir>/scene_1.jpg ... scene_N.jpg
"""
import os, sys, time, urllib.parse, requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def make_visuals(scene_prompts: list[str], out_dir: str) -> list[str]:
    paths = []
    for i, prompt in enumerate(scene_prompts, 1):
        full = f"{prompt}, {config.VISUAL_STYLE}"
        url = (f"{config.POLLINATIONS_BASE}/{urllib.parse.quote(full)}"
               f"?width={config.IMAGE_W}&height={config.IMAGE_H}"
               f"&nologo=true&seed={i*7}")
        out_path = os.path.join(out_dir, f"scene_{i}.jpg")
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=120)
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    f.write(r.content)
                paths.append(out_path)
                print(f"[visual] scene {i} -> {out_path}")
                break
            except Exception as e:
                print(f"[visual] scene {i} attempt {attempt+1} failed: {e}")
                time.sleep(5)
        else:
            raise RuntimeError(f"Pollinations failed for scene {i}")
    return paths


if __name__ == "__main__":
    import json
    d = sys.argv[1]
    script = json.load(open(os.path.join(d, "script.json")))
    make_visuals(script["scene_prompts"], d)
