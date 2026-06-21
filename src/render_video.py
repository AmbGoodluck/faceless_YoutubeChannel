"""
Stage 4 — Assemble the full video with FFmpeg (FREE).
Combines scene images (with a slow Ken-Burns zoom) + the voiceover + burned captions
into one vertical MP4 sized to the audio length.

Requires ffmpeg. Produces: <out_dir>/final.mp4
"""
import os, sys, json, subprocess

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _audio_dur(path: str) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nk=1:nw=1", path])
    return float(out.strip())


def render(out_dir: str) -> str:
    script = json.load(open(os.path.join(out_dir, "script.json")))
    # captions follow the edited narration.txt if present
    nt = os.path.join(out_dir, "narration.txt")
    narration = open(nt).read().strip() if os.path.exists(nt) else script["narration"]
    voice = os.path.join(out_dir, "voice.mp3")
    scenes = sorted(
        [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.startswith("scene_")])
    if not scenes:
        raise RuntimeError("No scene images. Run generate_visuals first.")

    total = _audio_dur(voice)
    per = total / len(scenes)
    W, H = config.IMAGE_W, config.IMAGE_H
    fps = 30
    frames = int(per * fps)

    # Build one zooming clip per image, then concat.
    parts = []
    for i, img in enumerate(scenes):
        clip = os.path.join(out_dir, f"_clip_{i}.mp4")
        # Single image in, zoompan emits exactly `frames` frames (no -loop, which
        # would multiply the input stream by `frames` and explode the length).
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"zoompan=z='min(zoom+0.0012,1.2)':d={frames}:s={W}x{H}:fps={fps}")
        subprocess.run([
            "ffmpeg", "-y", "-i", img,
            "-vf", vf, "-frames:v", str(frames),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), clip,
        ], check=True)
        parts.append(clip)

    concat_txt = os.path.join(out_dir, "_concat.txt")
    with open(concat_txt, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    silent = os.path.join(out_dir, "_silent.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
                    "-c", "copy", silent], check=True)

    # Captions: write a styled .ass (styling baked in, so the ffmpeg filter arg is
    # just the filename — no fragile force_style string to escape).
    ass = os.path.join(out_dir, "captions.ass")
    _even_ass(narration, total, ass, W, H)

    final = os.path.join(out_dir, "final.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", silent, "-i", voice,
        "-vf", f"subtitles={ass}",
        "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", final,
    ], check=True)

    # cleanup temp
    for p in parts + [silent, concat_txt]:
        try: os.remove(p)
        except OSError: pass
    print(f"[render] {final}")
    return final


def _even_ass(text: str, total: float, path: str, W: int, H: int, max_chars=38):
    # chunk narration into caption lines, distribute time by character share
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    total_chars = sum(len(l) for l in lines) or 1

    def ts(s):
        h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
        return f"{h:d}:{m:02d}:{sec:05.2f}"

    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {W}\nPlayResY: {H}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,56,&H00D8E4E8,&H00000000,&H64000000,-1,0,0,0,"
        "100,100,0,0,1,3,1,2,80,80,300,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

    t = 0.0
    with open(path, "w") as f:
        f.write(header)
        for l in lines:
            dur = total * (len(l) / total_chars)
            f.write(f"Dialogue: 0,{ts(t)},{ts(t+dur)},Default,,0,0,0,,{l}\n")
            t += dur


if __name__ == "__main__":
    render(sys.argv[1])
