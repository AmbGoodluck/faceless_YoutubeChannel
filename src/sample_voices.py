"""
Audition narrator voices. Synthesizes the same line in each candidate voice so you
can pick. Run:  python src/sample_voices.py
Then set TTS_VOICE in config.py to the one you like.
"""
import os, sys, asyncio, subprocess
import edge_tts

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

LINE = ("She should have locked the door. By the time she understood why, "
        "it was already too late.")
OUT = "voice_samples"


async def _synth(voice, path):
    await edge_tts.Communicate(LINE, voice, rate=config.TTS_RATE,
                               pitch=config.TTS_PITCH).save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    for v in config.VOICE_CANDIDATES:
        p = os.path.join(OUT, f"{v}.mp3")
        asyncio.run(_synth(v, p))
        print(f"[voice] {v} -> {p}")
    print(f"\nListen to the clips in ./{OUT}/ , then set TTS_VOICE in config.py.")
    if sys.platform == "darwin":
        subprocess.run(["open", OUT])   # opens the folder in Finder


if __name__ == "__main__":
    main()
