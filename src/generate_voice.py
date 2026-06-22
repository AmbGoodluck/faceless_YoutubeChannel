"""
Stage 3a — Multi-voice screenplay narration via Microsoft Edge TTS (FREE).
Each line is spoken in its character's assigned voice (Narrator uses config.TTS_VOICE),
then all lines are stitched into one voice.mp3.

Reads the editable screenplay in <out_dir>/narration.txt (SPEAKER: line per row).
"""
from __future__ import annotations
import os, sys, asyncio, subprocess
import edge_tts

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import generate_script


async def _synth(text, voice, path):
    await edge_tts.Communicate(text, voice, rate=config.TTS_RATE, pitch=config.TTS_PITCH).save(path)


def make_voice(out_dir: str, voice_map: dict | None = None) -> str:
    vm = {k.upper(): v for k, v in (voice_map or {}).items()}
    lines = generate_script.parse_screenplay(out_dir)
    parts = []
    for i, (speaker, text) in enumerate(lines):
        if not text.strip():
            continue
        voice = config.TTS_VOICE if speaker.upper() == "NARRATOR" else vm.get(speaker.upper(), config.TTS_VOICE)
        p = os.path.join(out_dir, f"_line_{i:03d}.mp3")
        asyncio.run(_synth(text, voice, p))
        parts.append(p)

    concat = os.path.join(out_dir, "_voice_concat.txt")
    with open(concat, "w") as f:
        f.write("\n".join(f"file '{os.path.abspath(p)}'" for p in parts))
    out = os.path.join(out_dir, "voice.mp3")
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", out], check=True)
    except subprocess.CalledProcessError:
        # re-encode if stream-copy concat fails (mismatched params)
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", concat,
                        "-c:a", "libmp3lame", "-q:a", "4", out], check=True)
    for p in parts + [concat]:
        try: os.remove(p)
        except OSError: pass
    print(f"[voice] {len(parts)} lines -> {out}")
    return out


if __name__ == "__main__":
    import json
    d = sys.argv[1]
    vm = json.load(open(os.path.join(d, "script.json"))).get("voice_map", {})
    make_voice(d, vm)
