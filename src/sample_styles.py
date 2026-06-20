"""
Style comparison — generates ONE real sample image per style from the same scene,
so you can pick the look before committing. Saves to style_samples/ and opens them.

Usage:  python src/sample_styles.py
Then set ACTIVE_STYLE in config.py to the one you like.
"""
import os, sys, time, urllib.parse, subprocess, requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SCENE = ("empty fourth floor apartment hallway at night, a single folded note "
         "on the floor, one dim doorway of light at the end")
OUT = "style_samples"


def main():
    os.makedirs(OUT, exist_ok=True)
    made = []
    for name, style in config.STYLES.items():
        prompt = f"{SCENE}, {style}"
        url = (f"{config.POLLINATIONS_BASE}/{urllib.parse.quote(prompt)}"
               f"?width={config.IMAGE_W}&height={config.IMAGE_H}&nologo=true&seed=42")
        path = os.path.join(OUT, f"{name}.jpg")
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=120); r.raise_for_status()
                open(path, "wb").write(r.content)
                made.append(path); print(f"[sample] {name} -> {path}"); break
            except Exception as e:
                print(f"[sample] {name} attempt {attempt+1} failed: {e}"); time.sleep(5)
    # open them for a side-by-side look (macOS 'open', Linux 'xdg-open')
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    for p in made:
        try: subprocess.run([opener, p])
        except Exception: pass
    print(f"\nDone. Compare the 4 images in ./{OUT}/ , then set ACTIVE_STYLE in config.py.")


if __name__ == "__main__":
    main()
