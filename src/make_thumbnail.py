"""
Generate a YouTube thumbnail (1280x720) for an episode, in the Lights Out Tales
brand style: charcoal background, amber hanging bulb, punchy typewriter text.

Produces: <out_dir>/thumbnail.jpg
"""
import os, sys, json
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

CHARCOAL = (14, 14, 16)
BONE = (232, 228, 216)
AMBER = (200, 147, 43)
AMBER_HI = (240, 190, 90)
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
# macOS fallback if the DejaVu path isn't present:
if not os.path.exists(MONO):
    for p in ["/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
              "/Library/Fonts/Arial Bold.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]:
        if os.path.exists(p):
            MONO = p; break


def _glow(size, center, r, color, intensity, blur):
    g = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    cx, cy = center
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (intensity,))
    return g.filter(ImageFilter.GaussianBlur(blur))


def make(out_dir: str) -> str:
    script = json.load(open(os.path.join(out_dir, "script.json")))
    text = script.get("thumbnail_text") or script.get("title", "LIGHTS OUT")
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), CHARCOAL).convert("RGBA")
    # amber bulb glow on the right third
    bx, by = int(W * 0.78), int(H * 0.42)
    img = Image.alpha_composite(img, _glow((W, H), (bx, by), 360, AMBER, 90, 220))
    img = Image.alpha_composite(img, _glow((W, H), (bx, by), 120, AMBER_HI, 150, 90))
    d = ImageDraw.Draw(img)
    d.line([(bx, 0), (bx, by - 70)], fill=(70, 67, 62), width=4)
    for rr, col in [(60, (120, 86, 28)), (48, AMBER), (34, AMBER_HI), (18, (255, 224, 160))]:
        d.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=col)
    # left scrim for text legibility
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    for x in range(int(W * 0.62)):
        sd.line([(x, 0), (x, H)], fill=(0, 0, 0, int(170 * (1 - x / (W * 0.62)))))
    img = Image.alpha_composite(img, scrim)
    d = ImageDraw.Draw(img)
    # wrap thumbnail_text to ~12 chars/line, big
    words, lines, cur = text.upper().split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= 13:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    fsize = 120 if max((len(l) for l in lines), default=0) <= 9 else 92
    font = ImageFont.truetype(MONO, fsize)
    y = H // 2 - (len(lines) * (fsize + 10)) // 2
    d.rectangle([60, y - 20, 70, y + len(lines) * (fsize + 10)], fill=AMBER_HI)
    for ln in lines:
        d.text((100, y), ln, font=font, fill=BONE)
        y += fsize + 10
    # brand tag bottom-left
    small = ImageFont.truetype(MONO, 30)
    d.text((100, H - 60), "LIGHTS OUT TALES", font=small, fill=(154, 150, 140))
    out = os.path.join(out_dir, "thumbnail.jpg")
    img.convert("RGB").save(out, quality=90)
    print(f"[thumbnail] {out}")
    return out


if __name__ == "__main__":
    make(sys.argv[1])
