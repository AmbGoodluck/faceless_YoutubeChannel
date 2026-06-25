"""
Amadu Studios — Main Orchestrator
Production-centric AI film pipeline for Lights Out Tales.

Usage:
  python amadu_studios/run.py --new               # create new production + generate Part 1
  python amadu_studios/run.py --new --title "X"   # new production with a specific title
  python amadu_studios/run.py --part <N>           # generate + render a specific part
  python amadu_studios/run.py --render <N>         # re-render already-scripted part
  python amadu_studios/run.py --preview <N>        # open Part N video in default player
  python amadu_studios/run.py --publish <N>        # upload Part N to YouTube
  python amadu_studios/run.py --auto               # generate today's next pending part
  python amadu_studios/run.py --status             # print production status

Agent pipeline per part:
  Producer (once) → Director → Writer → Cinematographer + Lighting
  → Renderer (image + video) → Continuity Supervisor → Editor → Publisher

FIX LOG:
  - Fixed broken db.update_episode() triple-ternary on old line 317.
  - Fixed voice: _generate_voice() now writes narration.txt in the format
    parse_screenplay() actually expects (SPEAKER: text) then calls make_voice().
  - Removed unused 'generate_script' import in _assemble().
  - Added --publish handler (was defined in argparse but never executed).
  - Added --auto daily mode.
  - Added VIDEO_PROVIDER env-var override for renderer selection.
"""
from __future__ import annotations
import os, sys, json, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from amadu_studios.database import db
from amadu_studios.agents import producer, director, writer, cinematographer, lighting
from amadu_studios.agents import state_engine, vision_qa
from amadu_studios.renderers.base import get_renderer
from amadu_studios.continuity import supervisor
import config

OUTPUT_ROOT = os.path.join(config.OUTPUT_DIR, "amadu")


def _out_dir(prod_id: int, part_num: int) -> str:
    prod = db.get_production(prod_id)
    slug = prod["title"].lower().replace(" ", "-").replace("'", "").replace(":", "")[:30]
    path = os.path.join(OUTPUT_ROOT, f"p{prod_id}-{slug}", f"part{part_num:02d}")
    os.makedirs(path, exist_ok=True)
    return path


def _get_active_prod() -> dict:
    prod = db.latest_production()
    if not prod:
        print("[run] No production found. Run --new first.")
        sys.exit(1)
    return prod


# ── Stage: New Production ────────────────────────────────────────────────────

def cmd_new(title: str = None):
    db.init()
    prod = producer.run(title=title, parts=config.PARTS_PER_STORY)
    print(f"\n[run] Production created: #{prod['id']} — {prod['title']}")
    cmd_part(prod["id"], 1)


# ── Stage: Full Part (script + render) ──────────────────────────────────────

def cmd_part(prod_id: int, part_num: int):
    """Run all agents for one part: script → voice → render → continuity → assemble."""
    prod = db.get_production(prod_id)
    print(f"\n{'='*60}")
    print(f"AMADU STUDIOS: {prod['title']} — Part {part_num}")
    print(f"{'='*60}")

    ep = db.get_episode(prod_id, part_num)
    if not ep:
        print(f"[run] Part {part_num} beat not found in production #{prod_id}")
        sys.exit(1)
    ep_id = ep["id"]
    out_dir = _out_dir(prod_id, part_num)

    # 1. Director: Scene DNA
    print(f"\n[run] Stage 1/6 — Director (Scene DNA)...")
    scenes = director.run(prod_id, ep_id, part_num)
    print(f"[run] {len(scenes)} scenes planned")

    # 2. Writer: Screenplay
    print(f"\n[run] Stage 2/6 — Writer (Screenplay)...")
    lines = writer.run(prod_id, ep_id, part_num)

    # 3. Voice
    print(f"\n[run] Stage 3/6 — Audio (Voice)...")
    voice_path = _generate_voice(ep_id, out_dir)

    # 4. Cinematographer + Lighting → shots in DB → Renderer
    print(f"\n[run] Stage 4/6 — Cinematographer + Lighting + Renderer...")
    # Allow env-var override: VIDEO_PROVIDER=kling python amadu_studios/run.py --part 1
    renderer_mode = os.environ.get("VIDEO_PROVIDER") or config.VIDEO_MODE
    renderer = get_renderer(renderer_mode)
    print(f"[run] renderer: {renderer.name} (mode: {renderer_mode})")

    characters = db.get_characters(prod_id)
    char_map = {c["id"]: c for c in characters}

    shot_count  = 0
    failed_shots = []   # (shot_id, prompt, out_dir) — for auto-rerender pass

    for scene in scenes:
        location = None
        with db.tx() as conn:
            row = conn.execute("SELECT * FROM locations WHERE id=?",
                               (scene["location_id"],)).fetchone()
            if row:
                location = dict(row)
        if not location:
            print(f"[run] WARNING: no location found for scene {scene['scene_num']} "
                  f"(location_id={scene['location_id']}), skipping")
            continue

        char_ids    = json.loads(scene.get("characters_json", "[]"))
        scene_chars = [char_map[cid] for cid in char_ids if cid in char_map]
        loc_id      = scene.get("location_id")

        wardrobes = {c["id"]: db.get_wardrobe_for_part(c["id"], part_num) or ""
                     for c in scene_chars}

        # ── LAYER 1: State engine — read current state BEFORE planning shots ──
        # States from previous scenes are already in the DB.
        # First scene of the part reads from the previous part's final state.
        states = state_engine.get_states_for_scene(char_ids, part_num, scene["scene_num"])

        n_shots    = max(3, config.SHOTS_PER_PART // max(1, len(scenes)))
        shot_specs = cinematographer.plan_shots(scene, n_shots=n_shots)

        for spec in shot_specs:
            light_desc, colour_grade = lighting.assign(
                time_of_day=scene.get("time_of_day", "night"),
                weather=scene.get("weather", "clear"),
                emotional_arc=scene.get("emotional_arc", "dread"),
                shot_type=spec["shot_type"],
                scene_objective=scene.get("objective", ""),
            )

            prompt = cinematographer.assemble_prompt(
                shot={"shot_type": spec["shot_type"], "lens": spec["lens"],
                      "emotion": spec["emotion"], "camera_movement": spec["camera_movement"]},
                scene=scene,
                location=location,
                characters=scene_chars,
                wardrobes=wardrobes,
                states=states,
                lighting_desc=light_desc,
                colour_grade=colour_grade,
            )

            shot_id = db.create_shot(
                scene_id=scene["id"],
                shot_num=spec["shot_num"],
                shot_type=spec["shot_type"],
                camera_movement=spec["camera_movement"],
                lens=spec["lens"],
                framing_note=spec["framing_note"],
                lighting_setup=light_desc,
                emotion=spec["emotion"],
                colour_grade=colour_grade,
                prompt=prompt,
            )

            # ── LAYER 2: Character/location seed pinning ──────────────────────
            # Face shots use the primary character's deterministic seed so
            # Pollinations generates a more consistent face across all shots.
            # Wide shots use the location's seed for environmental consistency.
            seed = vision_qa.resolve_seed(spec["shot_type"], char_ids, loc_id, shot_id)

            try:
                img_path = renderer.render_image(shot_id, prompt, out_dir, seed=seed)

                # ── LAYER 3: Vision QA ────────────────────────────────────────
                vqa = vision_qa.check_image(shot_id, img_path)
                if vqa["passed"]:
                    # Register canonical portraits / location anchors on first good render
                    vision_qa.register_reference_image(
                        shot_id, char_ids, loc_id, spec["shot_type"], img_path)

                if renderer.supports_video:
                    renderer.render_video(shot_id, img_path, prompt, out_dir)

                shot_count += 1

            except Exception as e:
                print(f"[run] render failed for shot {shot_id}: {e}")
                db.update_shot(shot_id, render_status="render_failed")
                failed_shots.append((shot_id, prompt, out_dir, char_ids, loc_id, spec["shot_type"]))

        # ── LAYER 4: State engine — update states AFTER scene completes ──────
        # Infers injuries/fatigue/emotional state from the scene objective and
        # writes to DB so the NEXT scene's prompts pick up the changes.
        state_engine.update_scene_states(
            ep_id=ep_id,
            scene_id=scene["id"],
            part_num=part_num,
            scene_num=scene["scene_num"],
        )

    # ── LAYER 5: Auto-rerender failed shots (one retry pass) ─────────────────
    if failed_shots:
        print(f"\n[run] Auto-rerender: {len(failed_shots)} failed shots, retrying...")
        retried = 0
        for shot_id, prompt, shot_out_dir, char_ids, loc_id, shot_type in failed_shots:
            seed = vision_qa.resolve_seed(shot_type, char_ids, loc_id, shot_id)
            try:
                img_path = renderer.render_image(shot_id, prompt, shot_out_dir, seed=seed)
                vqa = vision_qa.check_image(shot_id, img_path)
                if vqa["passed"]:
                    vision_qa.register_reference_image(
                        shot_id, char_ids, loc_id, shot_type, img_path)
                if renderer.supports_video:
                    renderer.render_video(shot_id, img_path, prompt, shot_out_dir)
                shot_count += 1
                retried += 1
            except Exception as e:
                print(f"[run] retry failed for shot {shot_id}: {e}")
                db.update_shot(shot_id, render_status="render_failed_permanent")
        print(f"[run] Retry pass: {retried}/{len(failed_shots)} recovered")

    print(f"[run] {shot_count}/{config.SHOTS_PER_PART} shots rendered")

    # 5. Continuity check
    print(f"\n[run] Stage 5/6 — Continuity Supervisor...")
    results = supervisor.check_episode(ep_id, prod_id, part_num)
    if results["failed"] > 0:
        print(f"[run] WARNING: {results['failed']} shots failed continuity")

    # 6. FFmpeg assembly
    print(f"\n[run] Stage 6/6 — Editor (FFmpeg assembly)...")
    final = _assemble(ep_id, prod_id, part_num, out_dir)

    ep_data = db.get_episode(prod_id, part_num)
    print(f"\n{'='*60}")
    print(f"DONE  ➜  {final}")
    print(f"Title: {ep_data.get('youtube_title', '')}")
    print(f"Shots: {shot_count} | Continuity: {results['passed']}/{results['total']} passed")
    print(f"\n  Preview:  python amadu_studios/run.py --preview {part_num}")
    print(f"  Publish:  python amadu_studios/run.py --publish {part_num}")
    print(f"{'='*60}\n")
    return final


# ── Voice generation ──────────────────────────────────────────────────────────

def _generate_voice(ep_id: int, out_dir: str) -> str:
    """
    Write narration.txt then call the existing Edge TTS voice module.

    FIX: parse_screenplay() in src/generate_voice.py reads SPEAKER: text lines.
    We write the file in that exact format. The module handles multi-line per speaker.
    """
    voice_path = os.path.join(out_dir, "voice.mp3")
    if os.path.exists(voice_path):
        print(f"[voice] cached at {voice_path}")
        return voice_path

    lines = db.get_screenplay(ep_id)
    if not lines:
        raise RuntimeError("No screenplay lines in DB — run writer agent first")

    # Write narration.txt in format expected by src/generate_voice.py:parse_screenplay()
    # Format: "SPEAKER: text\n" — one line per speech act
    narration_path = os.path.join(out_dir, "narration.txt")
    with open(narration_path, "w", encoding="utf-8") as f:
        for l in lines:
            speaker = l.get("speaker", "Narrator").strip()
            text    = l.get("text", "").strip()
            if text:
                f.write(f"{speaker}: {text}\n")

    # Build voice_map: SPEAKER_NAME_UPPER -> edge_tts_voice_string
    voice_map = {}
    for l in lines:
        spk = l.get("speaker", "").strip().upper()
        vid = l.get("voice_id", "")
        if spk and vid:
            voice_map[spk] = vid

    # Call the existing voice module from the old pipeline.
    # generate_voice.make_voice() creates _line_NNN.mp3 files then concatenates
    # them into voice.mp3. We do NOT delete the _line_NNN.mp3 files afterwards —
    # the lip-sync renderer needs them to extract per-character audio segments.
    from src import generate_voice
    generate_voice.make_voice(out_dir, voice_map)

    # Verify individual line files exist (sanity check for lipsync renderer)
    import glob
    line_files = sorted(glob.glob(os.path.join(out_dir, "_line_*.mp3")))
    print(f"[voice] {len(line_files)} lines -> {voice_path}")
    return voice_path


# ── FFmpeg assembly ───────────────────────────────────────────────────────────

def _assemble(ep_id: int, prod_id: int, part_num: int, out_dir: str) -> str:
    shots = db.get_all_shots_for_episode(ep_id)
    voice_path = os.path.join(out_dir, "voice.mp3")
    final_path = os.path.join(out_dir, "final.mp4")

    if not os.path.exists(voice_path):
        raise RuntimeError("voice.mp3 missing — run voice stage first")

    # Collect rendered clips (prefer .mp4, fallback to Ken-Burns on .jpg)
    clips = []
    for shot in shots:
        vid = shot.get("video_path") or ""
        img = shot.get("image_path") or ""
        if vid and os.path.exists(vid):
            clips.append(vid)
        elif img and os.path.exists(img):
            renderer = get_renderer()
            try:
                clip = renderer.render_video(shot["id"], img, shot.get("prompt", ""), out_dir)
                if clip and os.path.exists(clip):
                    clips.append(clip)
            except Exception as e:
                print(f"[assemble] Ken-Burns fallback failed for shot {shot['id']}: {e}")

    if not clips:
        raise RuntimeError("No clips to assemble — check renderer logs")

    # Import FFmpeg helpers from old pipeline (render_video.py)
    from src import render_video as rv

    lines = db.get_screenplay(ep_id)
    narration = " ".join(l["text"] for l in lines if l.get("text"))

    import subprocess as sp
    W, H, fps = config.IMAGE_W, config.IMAGE_H, 30

    # Get voice duration
    dur_out = sp.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nk=1:nw=1", voice_path])
    total = float(dur_out.strip())

    X = config.CROSSFADE
    n = len(clips)
    per = (total + (n - 1) * X) / max(n, 1)

    # Re-encode clips to exact duration
    parts = []
    for i, src in enumerate(clips):
        clip_path = os.path.join(out_dir, f"_enc_{i}.mp4")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"tpad=stop_mode=clone:stop_duration={per:.2f}")
        sp.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", src, "-vf", vf, "-t", f"{per:.2f}", "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), clip_path], check=True)
        parts.append(clip_path)

    # Crossfade chain
    silent = os.path.join(out_dir, "_silent.mp4")
    grade  = config.FILM_GRADE
    inputs = []
    for p in parts:
        inputs += ["-i", p]
    fc, prev = [], "0:v"
    for k in range(1, n):
        off = k * (per - X)
        lbl = f"v{k}"
        fc.append(f"[{prev}][{k}:v]xfade=transition=fade:duration={X:.2f}:offset={off:.2f}[{lbl}]")
        prev = lbl
    fc.append(f"[{prev}]{grade}[vout]")
    try:
        sp.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
                "-filter_complex", ";".join(fc), "-map", "[vout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), silent], check=True)
    except sp.CalledProcessError:
        # Fallback: simple concat (no crossfades)
        concat_txt = os.path.join(out_dir, "_concat.txt")
        with open(concat_txt, "w") as f:
            for p in parts:
                f.write(f"file '{os.path.abspath(p)}'\n")
        tmp = os.path.join(out_dir, "_cat.mp4")
        sp.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", tmp], check=True)
        sp.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", tmp, "-vf", grade, "-c:v", "libx264", "-pix_fmt", "yuv420p", silent],
               check=True)

    # Burn captions + mix audio
    ass_path = os.path.join(out_dir, "captions.ass")
    rv._even_ass(narration, total, ass_path, W, H)
    # FFmpeg subtitles filter requires absolute path; on macOS colons in the path
    # must be escaped as \: — use a separate -vf input file trick to avoid this entirely.
    abs_ass = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")
    try:
        sp.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", silent, "-i", voice_path,
                "-vf", f"subtitles='{abs_ass}'",
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-shortest", final_path], check=True)
    except sp.CalledProcessError:
        # Fallback: no captions
        sp.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", silent, "-i", voice_path,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", final_path],
               check=True)

    # Cleanup temp re-encoded clips only (_enc_N.mp4, _silent.mp4, _concat.txt)
    # Do NOT delete _line_NNN.mp3 files — lipsync renderer needs them
    for p in parts:
        try:
            os.remove(p)
        except OSError:
            pass
    for tmp in ["_silent.mp4", "_cat.mp4", "_concat.txt", "_voice_concat.txt"]:
        try:
            os.remove(os.path.join(out_dir, tmp))
        except OSError:
            pass

    # FIX: was a broken triple-ternary — ep_id is directly in scope
    db.update_episode(ep_id, status="rendered")
    print(f"[editor] assembled -> {final_path}")
    return final_path


# ── Publish ───────────────────────────────────────────────────────────────────

def cmd_publish(part_num: int):
    """Upload Part N to YouTube using existing upload_youtube module."""
    prod = _get_active_prod()
    ep = db.get_episode(prod["id"], part_num)
    if not ep:
        print(f"[publish] No episode found for Part {part_num}")
        return

    out_dir    = _out_dir(prod["id"], part_num)
    final_path = os.path.join(out_dir, "final.mp4")
    if not os.path.exists(final_path):
        print(f"[publish] final.mp4 not found. Run --part {part_num} first.")
        return

    from src import upload_youtube
    title       = ep.get("youtube_title") or f"{prod['title']} — Part {part_num}"
    description = ep.get("youtube_desc") or ""
    hashtags    = json.loads(ep.get("hashtags") or "[]")
    tags        = hashtags[:15]  # YouTube allows up to 500 chars or ~15 tags

    print(f"[publish] uploading: {title}")
    video_id = upload_youtube.upload(
        video_path=final_path,
        title=title,
        description=description,
        tags=tags,
    )
    if video_id:
        db.update_episode(ep["id"], status="published")
        print(f"[publish] done — https://youtu.be/{video_id}")
        if ep.get("pinned_comment"):
            try:
                upload_youtube.pin_comment(video_id, ep["pinned_comment"])
            except Exception as e:
                print(f"[publish] pin comment failed (non-fatal): {e}")
    else:
        print("[publish] upload returned no video_id — check YouTube API logs")


# ── Auto daily mode ───────────────────────────────────────────────────────────

def cmd_auto():
    """
    Generate today's next pending part automatically.
    Designed for cron / GitHub Actions: runs once, picks up where the last part left off.
    """
    db.init()
    prod = db.latest_production()
    if not prod:
        print("[auto] No production found. Creating first production...")
        cmd_new()
        return

    next_part = db.next_pending_part(prod["id"])
    total     = prod.get("total_parts", config.PARTS_PER_STORY)

    if next_part > total:
        print(f"[auto] Production #{prod['id']} complete ({total} parts done). Starting new production...")
        cmd_new()
        return

    print(f"[auto] Production #{prod['id']}: generating Part {next_part}/{total}")
    cmd_part(prod["id"], next_part)


# ── Preview ───────────────────────────────────────────────────────────────────

def cmd_preview(part_num: int):
    prod = _get_active_prod()
    out_dir = _out_dir(prod["id"], part_num)
    final   = os.path.join(out_dir, "final.mp4")
    if not os.path.exists(final):
        print(f"No final.mp4 for Part {part_num}. Run --part {part_num} first.")
        return
    import platform
    opener = "open" if platform.system() == "Darwin" else "xdg-open"
    subprocess.Popen([opener, final])
    print(f"[preview] opening {final}")


# ── Status ────────────────────────────────────────────────────────────────────

def cmd_status():
    db.init()
    prod = db.latest_production()
    if not prod:
        print("No production found. Run --new to start.")
        return
    print(f"\n{'='*60}")
    print(f"Production #{prod['id']}: {prod['title']}")
    print(f"  Genre: {prod['genre']} | Parts: {prod['total_parts']} | Style: {prod['style_pack']}")
    print(f"  Setting: {prod['setting']}")
    print(f"  Logline: {prod['logline']}")
    chars = db.get_characters(prod["id"])
    print(f"\nCharacters ({len(chars)}):")
    for c in chars:
        print(f"  #{c['id']} {c['name']} ({c['role']}, {c['gender']}) — voice: {c['voice_id']}")
    locs = db.get_locations(prod["id"])
    print(f"\nLocations ({len(locs)}):")
    for l in locs:
        print(f"  #{l['id']} {l['name']}: {l['description'][:70]}...")
    print(f"\nParts status:")
    for n in range(1, prod["total_parts"] + 1):
        ep = db.get_episode(prod["id"], n)
        status = ep.get("status", "pending") if ep else "no beat"
        print(f"  Part {n:02d}: {status}")
    print(f"\nRenderer: {os.environ.get('VIDEO_PROVIDER', config.VIDEO_MODE)}")
    print(f"{'='*60}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Amadu Studios — AI film pipeline")
    p.add_argument("--new",     action="store_true", help="Create new production")
    p.add_argument("--title",   type=str,            help="Title for new production")
    p.add_argument("--part",    type=int,            help="Generate + render Part N")
    p.add_argument("--render",  type=int,            help="Re-render already-scripted Part N")
    p.add_argument("--preview", type=int,            help="Open Part N in media player")
    p.add_argument("--publish", type=int,            help="Upload Part N to YouTube")
    p.add_argument("--auto",    action="store_true", help="Generate next pending part (for cron)")
    p.add_argument("--status",  action="store_true", help="Show production status")
    a = p.parse_args()

    if a.new:
        cmd_new(title=a.title)
    elif a.part:
        prod = _get_active_prod()
        cmd_part(prod["id"], a.part)
    elif a.render:
        prod = _get_active_prod()
        out_dir = _out_dir(prod["id"], a.render)
        ep = db.get_episode(prod["id"], a.render)
        if not ep:
            print(f"No episode for Part {a.render}")
            sys.exit(1)
        _assemble(ep["id"], prod["id"], a.render, out_dir)
    elif a.preview:
        cmd_preview(a.preview)
    elif a.publish:
        cmd_publish(a.publish)
    elif a.auto:
        cmd_auto()
    elif a.status:
        cmd_status()
    else:
        p.print_help()


if __name__ == "__main__":
    main()
