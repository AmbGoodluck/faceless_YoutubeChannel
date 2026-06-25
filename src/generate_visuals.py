"""
Stage 3b — Scene images via Pollinations.ai (FREE, no API key).
One image per shot, in the channel's dark cinematic style.

Character appearance is already injected into each prompt by generate_script.py
(_inject_char_refs), so consistency is maintained across all parts without
any extra work here.

Hollywood 5 criteria (lighting, depth, leading lines, emotion, colour grade)
are encoded in config.VISUAL_STYLE ("photoreal") and added as a suffix to every prompt.

Produces: <out_dir>/scene_1.jpg ... scene_N.jpg
"""
import os, sys, time, urllib.parse, requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def make_visuals(scene_prompts: list[str], out_dir: str) -> list[str]:
    """Generate one image per shot. Returns list of saved image paths."""
    paths = []
    for i, prompt in enumerate(scene_prompts, 1):
        out_path = os.path.join(out_dir, f"scene_{i}.jpg")
        if os.path.exists(out_path):
            print(f"[visual] scene {i} already exists, skipping")
            paths.append(out_path)
            continue

        # Character descriptions are already prepended in the prompt.
        # Append the VISUAL_STYLE suffix (Hollywood 5 criteria + film look).
        full = f"{prompt}, {config.VISUAL_STYLE}"
        url = (f"{config.POLLINATIONS_BASE}/{urllib.parse.quote(full)}"
               f"?width={config.IMAGE_W}&height={config.IMAGE_H}"
               f"&nologo=true&seed={i * 13}")   # consistent seed per shot number
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=120)
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    f.write(r.content)
                paths.append(out_path)
                print(f"[visual] scene {i}/{len(scene_prompts)} -> {out_path}")
                time.sleep(1)   # gentle rate-limiting
                break
            except Exception as e:
                print(f"[visual] scene {i} attempt {attempt+1}/3 failed: {e}")
                time.sleep(5)
        else:
            raise RuntimeError(f"Pollinations failed for scene {i} after 3 attempts")
    return paths


if __name__ == "__main__":
    import json, sys
    d = sys.argv[1]
    script = json.load(open(os.path.join(d, "script.json")))
    make_visuals(script["scene_prompts"], d)
