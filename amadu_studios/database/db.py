"""
Amadu Studios — Database Layer
SQLite-backed persistent store. Every production asset, agent decision,
render, and continuity check is recorded here with full history.

Principle: assets are the source of truth. Every prompt is derived from
the database, never manually authored.
"""
from __future__ import annotations
import sqlite3, json, os, time
from contextlib import contextmanager
from typing import Optional

DB_PATH = os.environ.get("AMADU_DB", "amadu_studio.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def tx():
    """Context manager for a committed transaction."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    """Create all tables if they don't exist."""
    with tx() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS productions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            genre       TEXT,
            logline     TEXT,
            setting     TEXT,
            target_audience TEXT,
            total_parts INTEGER DEFAULT 20,
            style_pack  TEXT DEFAULT 'horror',
            created_at  REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS characters (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            production_id   INTEGER REFERENCES productions(id),
            name            TEXT NOT NULL,
            role            TEXT,
            gender          TEXT,
            appearance      TEXT,   -- prose description locked for the production
            voice_id        TEXT,   -- Edge TTS voice name
            reference_prompt TEXT,  -- Pollinations anchor prompt for this character
            created_at      REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS wardrobes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id    INTEGER REFERENCES characters(id),
            label           TEXT,           -- e.g. "default", "ep3_hospital"
            part_from       INTEGER DEFAULT 1,
            part_to         INTEGER DEFAULT 999,
            outfit          TEXT,           -- prose: "worn rust-orange knit sweater, dark olive cargo trousers..."
            active          INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS character_states (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id    INTEGER REFERENCES characters(id),
            part_num        INTEGER,
            scene_num       INTEGER,
            injuries        TEXT DEFAULT '',
            fatigue         TEXT DEFAULT 'none',
            clothing_note   TEXT DEFAULT '',
            emotional_state TEXT DEFAULT 'neutral',
            misc            TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS locations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            production_id   INTEGER REFERENCES productions(id),
            name            TEXT NOT NULL,
            description     TEXT,
            palette         TEXT,   -- "teal-and-amber, desaturated, crushed blacks"
            time_of_day     TEXT DEFAULT 'night',
            weather         TEXT DEFAULT 'clear',
            reference_prompt TEXT   -- anchor visual description for Pollinations
        );

        CREATE TABLE IF NOT EXISTS props (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            production_id   INTEGER REFERENCES productions(id),
            name            TEXT NOT NULL,
            description     TEXT,
            first_appears   INTEGER,    -- part number
            significance    TEXT
        );

        CREATE TABLE IF NOT EXISTS episodes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            production_id   INTEGER REFERENCES productions(id),
            part_num        INTEGER NOT NULL,
            title           TEXT,
            beat            TEXT,   -- what happens this part
            recap           TEXT,   -- recap of previous part
            youtube_title   TEXT,
            youtube_desc    TEXT,
            hashtags        TEXT,   -- JSON array
            thumbnail_text  TEXT,
            pinned_comment  TEXT,
            status          TEXT DEFAULT 'pending',   -- pending/scripted/rendered/published
            created_at      REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS scenes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id      INTEGER REFERENCES episodes(id),
            scene_num       INTEGER NOT NULL,
            location_id     INTEGER REFERENCES locations(id),
            time_of_day     TEXT,
            weather         TEXT,
            objective       TEXT,
            emotional_arc   TEXT,
            characters_json TEXT,   -- JSON array of character IDs present
            props_json      TEXT    -- JSON array of prop IDs present
        );

        CREATE TABLE IF NOT EXISTS shots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id        INTEGER REFERENCES scenes(id),
            shot_num        INTEGER NOT NULL,
            shot_type       TEXT,   -- ES/WS/MS/MCU/CU/ECU/OTS/POV/INSERT/TWO_SHOT
            camera_movement TEXT,
            lens            TEXT,
            framing_note    TEXT,
            lighting_setup  TEXT,
            emotion         TEXT,
            colour_grade    TEXT,
            prompt          TEXT,   -- ASSEMBLED from assets by cinematographer agent
            image_path      TEXT,
            video_path      TEXT,
            render_status   TEXT DEFAULT 'pending',
            continuity_ok   INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS renders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            shot_id         INTEGER REFERENCES shots(id),
            renderer        TEXT,
            attempt         INTEGER DEFAULT 1,
            status          TEXT,   -- pending/success/failed
            output_path     TEXT,
            error           TEXT,
            created_at      REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS continuity_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            shot_id         INTEGER REFERENCES shots(id),
            checks          TEXT,   -- JSON: {"character_appearance": true, "wardrobe": true, ...}
            passed          INTEGER DEFAULT 0,
            notes           TEXT,
            created_at      REAL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS screenplay_lines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id      INTEGER REFERENCES episodes(id),
            line_order      INTEGER,
            speaker         TEXT,
            text            TEXT,
            voice_id        TEXT
        );
        """)
        # ── Schema migrations: add new columns if the DB already existed ────────
        # SQLite does not support IF NOT EXISTS on ALTER TABLE, so we try/ignore.
        _MIGRATIONS = [
            "ALTER TABLE characters ADD COLUMN reference_image_path TEXT DEFAULT ''",
            "ALTER TABLE locations  ADD COLUMN reference_image_path TEXT DEFAULT ''",
        ]
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except Exception:
                pass   # column already present

    print(f"[db] initialised at {DB_PATH}")


# ── Productions ──────────────────────────────────────────────────────────────

def create_production(title: str, genre: str, logline: str, setting: str,
                      total_parts: int = 20, style_pack: str = "horror") -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO productions (title,genre,logline,setting,total_parts,style_pack) VALUES (?,?,?,?,?,?)",
            (title, genre, logline, setting, total_parts, style_pack))
        return cur.lastrowid


def get_production(prod_id: int) -> dict:
    with tx() as conn:
        row = conn.execute("SELECT * FROM productions WHERE id=?", (prod_id,)).fetchone()
        return dict(row) if row else None


def latest_production() -> Optional[dict]:
    with tx() as conn:
        row = conn.execute("SELECT * FROM productions ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None


# ── Characters ───────────────────────────────────────────────────────────────

def upsert_character(prod_id: int, name: str, role: str, gender: str,
                     appearance: str, voice_id: str, reference_prompt: str = "") -> int:
    with tx() as conn:
        existing = conn.execute(
            "SELECT id FROM characters WHERE production_id=? AND name=?", (prod_id, name)).fetchone()
        if existing:
            conn.execute(
                "UPDATE characters SET role=?,gender=?,appearance=?,voice_id=?,reference_prompt=? WHERE id=?",
                (role, gender, appearance, voice_id, reference_prompt, existing["id"]))
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO characters (production_id,name,role,gender,appearance,voice_id,reference_prompt) VALUES (?,?,?,?,?,?,?)",
            (prod_id, name, role, gender, appearance, voice_id, reference_prompt))
        return cur.lastrowid


def get_characters(prod_id: int) -> list[dict]:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM characters WHERE production_id=?", (prod_id,)).fetchall()
        return [dict(r) for r in rows]


def get_character(char_id: int) -> dict:
    with tx() as conn:
        row = conn.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
        return dict(row) if row else None


def set_character_reference_image(char_id: int, path: str):
    """Register a canonical portrait for this character (first good CU/MCU render)."""
    with tx() as conn:
        conn.execute("UPDATE characters SET reference_image_path=? WHERE id=?", (path, char_id))


def character_visual_seed(char_id: int) -> int:
    """Deterministic visual seed for Pollinations. Same seed + same prompt = same face."""
    return char_id * 997


# ── Wardrobes ────────────────────────────────────────────────────────────────

def set_wardrobe(char_id: int, label: str, outfit: str,
                 part_from: int = 1, part_to: int = 999) -> int:
    with tx() as conn:
        # deactivate any overlapping active wardrobe for this character
        conn.execute(
            "UPDATE wardrobes SET active=0 WHERE character_id=? AND label=?", (char_id, label))
        cur = conn.execute(
            "INSERT INTO wardrobes (character_id,label,part_from,part_to,outfit,active) VALUES (?,?,?,?,?,1)",
            (char_id, label, part_from, part_to, outfit))
        return cur.lastrowid


def get_wardrobe_for_part(char_id: int, part_num: int) -> Optional[str]:
    """Return the outfit string for this character at this part number."""
    with tx() as conn:
        row = conn.execute(
            "SELECT outfit FROM wardrobes WHERE character_id=? AND part_from<=? AND part_to>=? AND active=1 ORDER BY part_from DESC LIMIT 1",
            (char_id, part_num, part_num)).fetchone()
        return row["outfit"] if row else None


# ── Character State ───────────────────────────────────────────────────────────

def update_character_state(char_id: int, part_num: int, scene_num: int,
                            injuries: str = "", fatigue: str = "none",
                            clothing_note: str = "", emotional_state: str = "neutral",
                            misc: dict = None) -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO character_states (character_id,part_num,scene_num,injuries,fatigue,clothing_note,emotional_state,misc) VALUES (?,?,?,?,?,?,?,?)",
            (char_id, part_num, scene_num, injuries, fatigue, clothing_note, emotional_state, json.dumps(misc or {})))
        return cur.lastrowid


def get_character_state(char_id: int, part_num: int, scene_num: int) -> dict:
    with tx() as conn:
        row = conn.execute(
            "SELECT * FROM character_states WHERE character_id=? AND part_num<=? ORDER BY part_num DESC, scene_num DESC LIMIT 1",
            (char_id, part_num)).fetchone()
        return dict(row) if row else {"injuries": "", "fatigue": "none", "emotional_state": "neutral"}


# ── Locations ────────────────────────────────────────────────────────────────

def upsert_location(prod_id: int, name: str, description: str, palette: str,
                    time_of_day: str = "night", weather: str = "clear",
                    reference_prompt: str = "") -> int:
    with tx() as conn:
        existing = conn.execute(
            "SELECT id FROM locations WHERE production_id=? AND name=?", (prod_id, name)).fetchone()
        if existing:
            conn.execute(
                "UPDATE locations SET description=?,palette=?,time_of_day=?,weather=?,reference_prompt=? WHERE id=?",
                (description, palette, time_of_day, weather, reference_prompt, existing["id"]))
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO locations (production_id,name,description,palette,time_of_day,weather,reference_prompt) VALUES (?,?,?,?,?,?,?)",
            (prod_id, name, description, palette, time_of_day, weather, reference_prompt))
        return cur.lastrowid


def get_locations(prod_id: int) -> list[dict]:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM locations WHERE production_id=?", (prod_id,)).fetchall()
        return [dict(r) for r in rows]


def set_location_reference_image(loc_id: int, path: str):
    """Register the first good establishing shot as the location's canonical anchor."""
    with tx() as conn:
        conn.execute("UPDATE locations SET reference_image_path=? WHERE id=?", (path, loc_id))


def location_visual_seed(loc_id: int) -> int:
    """Deterministic visual seed for location establishing shots."""
    return loc_id * 7919


# ── Episodes ─────────────────────────────────────────────────────────────────

def create_episode(prod_id: int, part_num: int, title: str, beat: str,
                   recap: str = "") -> int:
    with tx() as conn:
        existing = conn.execute(
            "SELECT id FROM episodes WHERE production_id=? AND part_num=?", (prod_id, part_num)).fetchone()
        if existing:
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO episodes (production_id,part_num,title,beat,recap) VALUES (?,?,?,?,?)",
            (prod_id, part_num, title, beat, recap))
        return cur.lastrowid


def get_episode(prod_id: int, part_num: int) -> Optional[dict]:
    with tx() as conn:
        row = conn.execute(
            "SELECT * FROM episodes WHERE production_id=? AND part_num=?", (prod_id, part_num)).fetchone()
        return dict(row) if row else None


def update_episode(ep_id: int, **kwargs):
    if not kwargs: return
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [ep_id]
    with tx() as conn:
        conn.execute(f"UPDATE episodes SET {cols} WHERE id=?", vals)


def next_pending_part(prod_id: int) -> int:
    """Return the part number of the next part that hasn't been scripted yet."""
    with tx() as conn:
        row = conn.execute(
            "SELECT part_num FROM episodes WHERE production_id=? ORDER BY part_num DESC LIMIT 1",
            (prod_id,)).fetchone()
        return (row["part_num"] + 1) if row else 1


# ── Scenes ───────────────────────────────────────────────────────────────────

def create_scene(ep_id: int, scene_num: int, location_id: int, time_of_day: str,
                 weather: str, objective: str, emotional_arc: str,
                 character_ids: list[int], prop_ids: list[int] = None) -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO scenes (episode_id,scene_num,location_id,time_of_day,weather,objective,emotional_arc,characters_json,props_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (ep_id, scene_num, location_id, time_of_day, weather, objective, emotional_arc,
             json.dumps(character_ids), json.dumps(prop_ids or [])))
        return cur.lastrowid


def get_scenes(ep_id: int) -> list[dict]:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM scenes WHERE episode_id=? ORDER BY scene_num", (ep_id,)).fetchall()
        return [dict(r) for r in rows]


# ── Shots ────────────────────────────────────────────────────────────────────

def create_shot(scene_id: int, shot_num: int, shot_type: str, camera_movement: str,
                lens: str, framing_note: str, lighting_setup: str, emotion: str,
                colour_grade: str, prompt: str) -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO shots (scene_id,shot_num,shot_type,camera_movement,lens,framing_note,lighting_setup,emotion,colour_grade,prompt) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (scene_id, shot_num, shot_type, camera_movement, lens, framing_note, lighting_setup, emotion, colour_grade, prompt))
        return cur.lastrowid


def get_shots(scene_id: int) -> list[dict]:
    with tx() as conn:
        rows = conn.execute("SELECT * FROM shots WHERE scene_id=? ORDER BY shot_num", (scene_id,)).fetchall()
        return [dict(r) for r in rows]


def get_all_shots_for_episode(ep_id: int) -> list[dict]:
    with tx() as conn:
        rows = conn.execute("""
            SELECT sh.* FROM shots sh
            JOIN scenes sc ON sh.scene_id = sc.id
            WHERE sc.episode_id=?
            ORDER BY sc.scene_num, sh.shot_num
        """, (ep_id,)).fetchall()
        return [dict(r) for r in rows]


def update_shot(shot_id: int, **kwargs):
    if not kwargs: return
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [shot_id]
    with tx() as conn:
        conn.execute(f"UPDATE shots SET {cols} WHERE id=?", vals)


# ── Renders ───────────────────────────────────────────────────────────────────

def log_render(shot_id: int, renderer: str, attempt: int,
               status: str, output_path: str = "", error: str = "") -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO renders (shot_id,renderer,attempt,status,output_path,error) VALUES (?,?,?,?,?,?)",
            (shot_id, renderer, attempt, status, output_path, error))
        return cur.lastrowid


# ── Continuity ────────────────────────────────────────────────────────────────

def log_continuity(shot_id: int, checks: dict, passed: bool, notes: str = "") -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO continuity_reports (shot_id,checks,passed,notes) VALUES (?,?,?,?)",
            (shot_id, json.dumps(checks), int(passed), notes))
        if passed:
            conn.execute("UPDATE shots SET continuity_ok=1 WHERE id=?", (shot_id,))
        return cur.lastrowid


# ── Screenplay ────────────────────────────────────────────────────────────────

def save_screenplay(ep_id: int, lines: list[dict]):
    with tx() as conn:
        conn.execute("DELETE FROM screenplay_lines WHERE episode_id=?", (ep_id,))
        conn.executemany(
            "INSERT INTO screenplay_lines (episode_id,line_order,speaker,text,voice_id) VALUES (?,?,?,?,?)",
            [(ep_id, i, l.get("speaker","Narrator"), l.get("text",""), l.get("voice_id","")) for i, l in enumerate(lines)])


def get_screenplay(ep_id: int) -> list[dict]:
    with tx() as conn:
        rows = conn.execute(
            "SELECT * FROM screenplay_lines WHERE episode_id=? ORDER BY line_order", (ep_id,)).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    init()
    print("Schema OK.")
