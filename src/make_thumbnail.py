"""
Netflix-style YouTube thumbnail (1280x720 landscape): the episode's hero shot as the
backdrop, a cinematic dark gradient, a bold title treatment, the series name + episode,
and the channel mark. Looks like a streaming poster.

Produces: <out_dir>/thumbnail.jpg
"""
import os, sys, json, glob
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

W, H = 1280, 720
BONE = (238, 234, 226)
AMBER = (224, 168, 74)


def _font(size, bold=True):
    cands = ([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ] if bold else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for p in cands:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _backdrop(out_dir):
    imgs = sorted(glob.glob(os.path.join(out_dir, "scene_*.jpg")))
    if imgs:
        im = Image.open(imgs[0]).convert("RGB")
        # cover-crop to 16:9
        s = max(W / im.width, H / im.height)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        x = (im.width - W) // 2; y = (im.height - H) // 2
        return im.crop((x, y, x + W, y + H))
    return Image.new("RGB", (W, H), (12, 12, 14))


def _wrap(draw, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def make(out_dir: str) -> str:
    script = json.load(open(os.path.join(out_dir, "script.json")))
    yt = script.get("youtube_title", script.get("title", ""))
    series = yt.split("—")[0].strip() if "—" in yt else yt
    big = (script.get("thumbnail_text") or series).upper()

    img = _backdrop(out_dir).convert("RGBA")
    # cinematic darkening: bottom + left gradient for legibility
    grad = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(grad)
    for yy in range(H):
        gd.line([(0, yy), (W, yy)], fill=int(200 * (yy / H) ** 1.6))
    dark = Image.new("RGBA", (W, H), (6, 6, 9, 255))
    img = Image.composite(dark, img, grad)
    # subtle vignette
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-W * 0.2, -H * 0.2, W * 1.2, H * 1.2], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(160))
    img = Image.composite(img, Image.new("RGBA", (W, H), (0, 0, 0, 255)),
                          vig.point(lambda p: int(p * 0.85 + 38)))
    d = ImageDraw.Draw(img)

    # big title (wrapped), bottom-left, with shadow
    fsize = 132 if len(big) <= 11 else (104 if len(big) <= 18 else 80)
    f = _font(fsize)
    lines = _wrap(d, big, f, int(W * 0.82))
    lh = fsize + 12
    y = H - 150 - lh * len(lines)
    for ln in lines:
        d.text((62, y + 3), ln, font=f, fill=(0, 0, 0))      # shadow
        d.text((60, y), ln, font=f, fill=BONE)
        y += lh
    # accent bar
    d.rectangle([60, y + 8, 60 + min(360, int(W * 0.3)), y + 16], fill=AMBER)
    # series + episode line
    fs = _font(38)
    ep = ""
    if "Ep" in yt:
        ep = "  •  " + yt.split("—")[-1].strip()
    d.text((60, y + 30), (series + ep)[:80], font=fs, fill=BONE)
    # channel mark top-left
    d.text((60, 48), "LIGHTS OUT TALES", font=_font(28), fill=AMBER)

    out = os.path.join(out_dir, "thumbnail.jpg")
    img.convert("RGB").save(out, quality=92)
    print(f"[thumbnail] {out}")
    return out


if __name__ == "__main__":
    make(sys.argv[1])
