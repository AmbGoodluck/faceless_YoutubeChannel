"""
Stage 3a — Voiceover via Microsoft Edge TTS (FREE, unlimited, commercial-ok).
Install: pip install edge-tts   (already in requirements.txt)

Produces: <out_dir>/voice.mp3
"""
import os, sys, asyncio
import edge_tts

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


async def _synthesize(text: str, out_path: str):
    tts = edge_tts.Communicate(text, config.TTS_VOICE,
                               rate=config.TTS_RATE, pitch=config.TTS_PITCH)
    await tts.save(out_path)


def make_voice(narration: str, out_dir: str) -> str:
    out_path = os.path.join(out_dir, "voice.mp3")
    asyncio.run(_synthesize(narration, out_path))
    print(f"[voice] {out_path}")
    return out_path


if __name__ == "__main__":
    import json
    d = sys.argv[1]
    script = json.load(open(os.path.join(d, "script.json")))
    make_voice(script["narration"], d)
