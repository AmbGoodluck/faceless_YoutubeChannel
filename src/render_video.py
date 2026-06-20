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
        zoom = f"zoompan=z='min(zoom+0.0010,1.18)':d={frames}:s={W}x{H}:fps={fps}"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-t", f"{per:.2f}", "-i", img,
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{zoom}",
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

    # Captions: generate an SRT from the narration timed evenly across the audio,
    # then burn it. (Swap for Whisper word-timing later if you want perfect sync.)
    srt = os.path.join(out_dir, "captions.srt")
    _even_srt(script["narration"], total, srt)

    final = os.path.join(out_dir, "final.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", silent, "-i", voice,
        "-vf", (f"subtitles={srt}:force_style='Fontname=DejaVu Sans,Fontsize=14,"
                "PrimaryColour=&H00D8E4E8,OutlineColour=&H00000000,BorderStyle=1,"
                "Outline=2,Alignment=2,MarginV=120'"),
        "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", final,
    ], check=True)

    # cleanup temp
    for p in parts + [silent, concat_txt]:
        try: os.remove(p)
        except OSError: pass
    print(f"[render] {final}")
    return final


def _even_srt(text: str, total: float, path: str, max_chars=42):
    # chunk narration into caption lines, distribute time by character share
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    total_chars = sum(len(l) for l in lines) or 1
    t = 0.0
    def ts(s):
        h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
        return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")
    with open(path, "w") as f:
        for i, l in enumerate(lines, 1):
            dur = total * (len(l) / total_chars)
            f.write(f"{i}\n{ts(t)} --> {ts(t+dur)}\n{l}\n\n")
            t += dur


if __name__ == "__main__":
    render(sys.argv[1])
