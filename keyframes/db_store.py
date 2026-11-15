"""
Database storage and retrieval for VISTA-SL Sign Lessons & Keyframe VLM Analyses
(in both English and Greek, using "dominant hand" / "κυρίαρχο χέρι").

Stores all 109 lessons, their extracted keyframe images, geometric landmark analyses,
and bilingual VLM visual factor descriptions (handshape, placement, movement, mouth/facial expression)
into SQLite (`bot_database.db` & `database/bot_database.db`).

Supports:
  1. Saving all lessons & keyframes (`sync_to_db()`)
  2. Retrieving a specific lesson or the "next game / next lesson" (`get_lesson()`, `get_next_lesson()`)
  3. Retrieving top-k relevant sign entries for general sign-language Q&A (`retrieve_from_db()`)
"""
import os
import re
import json
import math
import sqlite3
import unicodedata
from datetime import datetime, timezone
from collections import Counter
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_FILE = os.path.join(HERE, "cache.json")
ENRICHED_FILE = os.path.join(HERE, "enriched.json")
PLATFORM_URL = os.getenv("PLATFORM_URL", "https://vistasl.eelvex.net").rstrip("/")

PRIMARY_DB_PATH = os.path.join(ROOT, "database", "bot_database.db")
ROOT_DB_PATH = os.path.join(ROOT, "bot_database.db")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _tokens(s: str) -> list[str]:
    return re.findall(r"\w+", _norm(s))


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_threads (
    user_id TEXT PRIMARY KEY,
    thread_slug TEXT
);

CREATE TABLE IF NOT EXISTS sign_lessons (
    lesson_id INTEGER PRIMARY KEY,
    seq_order INTEGER,
    title TEXT NOT NULL,
    module_id INTEGER,
    module_title TEXT,
    course_id INTEGER,
    course_title TEXT,
    lesson_url TEXT,
    video_url TEXT,
    local_video_path TEXT,
    has_reference INTEGER DEFAULT 0,
    keyframe_source TEXT,
    fps REAL,
    duration REAL,
    total_frames INTEGER,
    frame_indices_json TEXT,
    frame_images_json TEXT,
    geometric_analysis TEXT,
    hands TEXT,
    hands_el TEXT,
    handshape TEXT,
    handshape_el TEXT,
    palm_orientation TEXT,
    palm_orientation_el TEXT,
    location TEXT,
    location_el TEXT,
    mouth_and_face TEXT,
    mouth_and_face_el TEXT,
    movement TEXT,
    movement_el TEXT,
    key_features_json TEXT,
    key_features_el_json TEXT,
    common_mistakes_json TEXT,
    common_mistakes_el_json TEXT,
    learner_instructions TEXT,
    learner_instructions_el TEXT,
    per_keyframe_vlm_json TEXT,
    rag_chunk_text TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sign_lessons_title ON sign_lessons(title);
CREATE INDEX IF NOT EXISTS idx_sign_lessons_module ON sign_lessons(module_id);

CREATE TABLE IF NOT EXISTS sign_keyframes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL,
    frame_order INTEGER NOT NULL,
    frame_index INTEGER NOT NULL,
    timestamp_s REAL,
    image_path TEXT,
    vlm_handshape TEXT,
    vlm_handshape_el TEXT,
    vlm_placement TEXT,
    vlm_placement_el TEXT,
    vlm_mouth_face TEXT,
    vlm_mouth_face_el TEXT,
    vlm_notes TEXT,
    vlm_notes_el TEXT,
    UNIQUE(lesson_id, frame_index),
    FOREIGN KEY(lesson_id) REFERENCES sign_lessons(lesson_id) ON DELETE CASCADE
);
"""

_LESSON_EXTRA_COLS = [
    ("hands_el", "TEXT"),
    ("handshape_el", "TEXT"),
    ("palm_orientation_el", "TEXT"),
    ("location_el", "TEXT"),
    ("mouth_and_face_el", "TEXT"),
    ("movement_el", "TEXT"),
    ("key_features_el_json", "TEXT"),
    ("common_mistakes_el_json", "TEXT"),
    ("learner_instructions_el", "TEXT"),
]

_KF_EXTRA_COLS = [
    ("vlm_handshape_el", "TEXT"),
    ("vlm_placement_el", "TEXT"),
    ("vlm_mouth_face_el", "TEXT"),
    ("vlm_notes_el", "TEXT"),
]


def get_sqlite_conn(db_path: str = PRIMARY_DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = PRIMARY_DB_PATH):
    with get_sqlite_conn(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        # Ensure new bilingual columns exist if table was created earlier
        existing_l = {r[1] for r in conn.execute("PRAGMA table_info(sign_lessons)").fetchall()}
        for col, ctype in _LESSON_EXTRA_COLS:
            if col not in existing_l:
                conn.execute(f"ALTER TABLE sign_lessons ADD COLUMN {col} {ctype}")
        existing_k = {r[1] for r in conn.execute("PRAGMA table_info(sign_keyframes)").fetchall()}
        for col, ctype in _KF_EXTRA_COLS:
            if col not in existing_k:
                conn.execute(f"ALTER TABLE sign_keyframes ADD COLUMN {col} {ctype}")
        conn.commit()


def format_lesson_chunk(sign: dict, kf_meta: dict, enriched_entry: dict | None) -> str:
    lid = sign["lessonId"]
    title = sign["title"]
    vurl = (kf_meta or {}).get("video_url") or f"{PLATFORM_URL}/static/vid/teacher-video-{quote(title)}.mp4"
    f_imgs = (kf_meta or {}).get("frame_images") or []
    f_idxs = (kf_meta or {}).get("frame_indices") or []

    lines = [
        f"LESSON_ID: {lid}",
        f"TITLE: {title}",
        f"MODULE: {sign.get('moduleTitle', '')} (Module {sign.get('moduleId', '')})",
        f"COURSE: {sign.get('courseTitle', 'GSL - Level 1')}",
        f"LINK: {PLATFORM_URL}/lesson/{lid}",
    ]

    llm = (enriched_entry or {}).get("llm")
    if llm:
        lines.append(f"HOW TO SIGN '{title}' (ENGLISH - using dominant hand):")
        if llm.get("hands"):
            lines.append(f"- Hands: {llm['hands']}")
        if llm.get("handshape"):
            lines.append(f"- Handshape: {llm['handshape']}")
        if llm.get("palm_orientation"):
            lines.append(f"- Palm orientation: {llm['palm_orientation']}")
        if llm.get("location"):
            lines.append(f"- Placement / Location: {llm['location']}")
        mf = llm.get("mouth_and_facial_expression") or llm.get("mouth_and_face")
        if mf:
            lines.append(f"- Mouth & Facial Expression: {mf}")
        if llm.get("movement"):
            lines.append(f"- Movement: {llm['movement']}")
        if llm.get("key_features"):
            lines.append("- Important factors / Key features: " + "; ".join(llm["key_features"]))
        if llm.get("learner_instructions"):
            lines.append(f"- Step-by-step instructions: {llm['learner_instructions']}")

        if llm.get("learner_instructions_el") or llm.get("handshape_el"):
            lines.append(f"ΠΩΣ ΝΑ ΚΑΝΕΤΕ ΤΟ ΝΟΗΜΑ '{title}' (ΕΛΛΗΝΙΚΑ - με το κυρίαρχο χέρι):")
            if llm.get("hands_el"):
                lines.append(f"- Χέρια: {llm['hands_el']}")
            if llm.get("handshape_el"):
                lines.append(f"- Σχήμα χεριού: {llm['handshape_el']}")
            if llm.get("palm_orientation_el"):
                lines.append(f"- Προσανατολισμός παλάμης: {llm['palm_orientation_el']}")
            if llm.get("location_el"):
                lines.append(f"- Τοποθέτηση / Θέση: {llm['location_el']}")
            mf_el = llm.get("mouth_and_facial_expression_el") or llm.get("mouth_and_face_el")
            if mf_el:
                lines.append(f"- Στόμα & Έκφραση Προσώπου: {mf_el}")
            if llm.get("movement_el"):
                lines.append(f"- Κίνηση: {llm['movement_el']}")
            if llm.get("key_features_el"):
                lines.append("- Σημαντικοί παράγοντες / Βασικά χαρακτηριστικά: " + "; ".join(llm["key_features_el"]))
            if llm.get("learner_instructions_el"):
                lines.append(f"- Οδηγίες βήμα-βήμα: {llm['learner_instructions_el']}")

        lines.append(f"- Reference video: {vurl}")
    elif enriched_entry and enriched_entry.get("analysis"):
        lines.append(enriched_entry["analysis"])
    else:
        lines.append(f"HOW TO SIGN '{title}': Reference video: {vurl}")

    return "\n".join(lines)


def format_row_for_prompt(row: dict, lang: str = "en") -> str:
    """
    Format a `sign_lessons` DB row cleanly in the target language ('el' or 'en'),
    without exposing internal keyframe numbers, timestamps, or image file paths.
    """
    lid = row["lesson_id"]
    title = row["title"]
    link = row.get("lesson_url") or f"{PLATFORM_URL}/lesson/{lid}"
    vurl = row.get("video_url") or f"{PLATFORM_URL}/static/vid/teacher-video-{quote(title)}.mp4"

    if lang == "el" and (row.get("handshape_el") or row.get("learner_instructions_el")):
        kf_el = json.loads(row.get("key_features_el_json") or "[]")
        lines = [
            f"ΜΑΘΗΜΑ_ID: {lid}",
            f"ΤΙΤΛΟΣ: {title}",
            f"ΕΝΟΤΗΤΑ: {row.get('module_title', '')}",
            f"ΣΥΝΔΕΣΜΟΣ ΜΑΘΗΜΑΤΟΣ: {link}",
            f"ΠΩΣ ΓΙΝΕΤΑΙ ΤΟ ΝΟΗΜΑ '{title}':",
            f"- Χέρια: {row.get('hands_el') or row.get('hands') or ''}",
            f"- Σχήμα χεριού: {row.get('handshape_el') or ''}",
            f"- Προσανατολισμός παλάμης: {row.get('palm_orientation_el') or ''}",
            f"- Τοποθέτηση: {row.get('location_el') or ''}",
            f"- Στόμα & Έκφραση προσώπου: {row.get('mouth_and_face_el') or ''}",
            f"- Κίνηση: {row.get('movement_el') or ''}",
        ]
        if kf_el:
            lines.append("- Σημαντικοί παράγοντες: " + "; ".join(kf_el))
        if row.get("learner_instructions_el"):
            lines.append(f"- Οδηγίες εκτέλεσης: {row['learner_instructions_el']}")
        lines.append(f"- Βίντεο αναφοράς: {vurl}")
        return "\n".join(lines)

    kf_en = json.loads(row.get("key_features_json") or "[]")
    lines = [
        f"LESSON_ID: {lid}",
        f"TITLE: {title}",
        f"MODULE: {row.get('module_title', '')}",
        f"LESSON LINK: {link}",
        f"HOW TO SIGN '{title}':",
        f"- Hands: {row.get('hands') or ''}",
        f"- Handshape: {row.get('handshape') or ''}",
        f"- Palm orientation: {row.get('palm_orientation') or ''}",
        f"- Placement / Location: {row.get('location') or ''}",
        f"- Mouth & Facial Expression: {row.get('mouth_and_face') or ''}",
        f"- Movement: {row.get('movement') or ''}",
    ]
    if kf_en:
        lines.append("- Important factors: " + "; ".join(kf_en))
    if row.get("learner_instructions"):
        lines.append(f"- Instructions: {row['learner_instructions']}")
    lines.append(f"- Reference video: {vurl}")
    return "\n".join(lines)


def sync_to_db(cache_data: dict | None = None, enriched_data: dict | None = None) -> int:
    """
    Populates `sign_lessons` and `sign_keyframes` in both SQLite DB locations
    from `keyframes/cache.json` and `keyframes/enriched.json`.
    Returns number of lessons synced.
    """
    if cache_data is None:
        cache_data = json.load(open(CACHE_FILE, encoding="utf-8"))
    if enriched_data is None:
        enriched_data = json.load(open(ENRICHED_FILE, encoding="utf-8")) if os.path.exists(ENRICHED_FILE) else {}

    from keyframes.sign_describer import describe_sign

    signs = cache_data.get("signs") or []
    targets = cache_data.get("targets") or {}
    kf_meta_all = cache_data.get("keyframes_meta") or {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for db_path in (PRIMARY_DB_PATH, ROOT_DB_PATH):
        init_db(db_path)
        with get_sqlite_conn(db_path) as conn:
            for seq_idx, s in enumerate(signs, 1):
                lid = int(s["lessonId"])
                title = s["title"]
                meta = kf_meta_all.get(str(lid)) or {}
                target = targets.get(title)
                enriched = enriched_data.get(title) or {}
                llm = enriched.get("llm") or {}

                geo_analysis = enriched.get("analysis") or (describe_sign(target) if target else "")
                vurl = meta.get("video_url") or (target or {}).get("videoUrl") or (
                    f"{PLATFORM_URL}/static/vid/teacher-video-{quote(title)}.mp4"
                )
                f_indices = meta.get("frame_indices") or []
                f_images = meta.get("frame_images") or []
                fps = float(meta.get("fps") or 30.0)
                duration = float(meta.get("duration") or 0.0)
                total_frames = int(meta.get("total_frames") or 0)
                mouth_face = llm.get("mouth_and_facial_expression") or llm.get("mouth_and_face") or ""
                mouth_face_el = llm.get("mouth_and_facial_expression_el") or llm.get("mouth_and_face_el") or ""
                per_kf = llm.get("per_keyframe") or []

                chunk_text = format_lesson_chunk(s, meta, enriched)

                conn.execute(
                    """
                    INSERT OR REPLACE INTO sign_lessons (
                        lesson_id, seq_order, title, module_id, module_title,
                        course_id, course_title, lesson_url, video_url, local_video_path,
                        has_reference, keyframe_source, fps, duration, total_frames,
                        frame_indices_json, frame_images_json, geometric_analysis,
                        hands, hands_el, handshape, handshape_el,
                        palm_orientation, palm_orientation_el, location, location_el,
                        mouth_and_face, mouth_and_face_el, movement, movement_el,
                        key_features_json, key_features_el_json,
                        common_mistakes_json, common_mistakes_el_json,
                        learner_instructions, learner_instructions_el,
                        per_keyframe_vlm_json, rag_chunk_text, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        lid,
                        seq_idx,
                        title,
                        s.get("moduleId"),
                        s.get("moduleTitle"),
                        s.get("courseId", 1),
                        s.get("courseTitle", "GSL - Level 1"),
                        f"{PLATFORM_URL}/lesson/{lid}",
                        vurl,
                        meta.get("video_path"),
                        1 if s.get("hasReference") else 0,
                        meta.get("source", "motion_auto"),
                        fps,
                        duration,
                        total_frames,
                        json.dumps(f_indices, ensure_ascii=False),
                        json.dumps(f_images, ensure_ascii=False),
                        geo_analysis,
                        llm.get("hands"),
                        llm.get("hands_el"),
                        llm.get("handshape"),
                        llm.get("handshape_el"),
                        llm.get("palm_orientation"),
                        llm.get("palm_orientation_el"),
                        llm.get("location"),
                        llm.get("location_el"),
                        mouth_face,
                        mouth_face_el,
                        llm.get("movement"),
                        llm.get("movement_el"),
                        json.dumps(llm.get("key_features") or [], ensure_ascii=False),
                        json.dumps(llm.get("key_features_el") or [], ensure_ascii=False),
                        json.dumps(llm.get("common_mistakes") or [], ensure_ascii=False),
                        json.dumps(llm.get("common_mistakes_el") or [], ensure_ascii=False),
                        llm.get("learner_instructions"),
                        llm.get("learner_instructions_el"),
                        json.dumps(per_kf, ensure_ascii=False),
                        chunk_text,
                        now_iso,
                    ),
                )

                conn.execute("DELETE FROM sign_keyframes WHERE lesson_id = ?", (lid,))
                pk_by_idx = {int(pk["frame_index"]): pk for pk in per_kf if isinstance(pk, dict) and str(pk.get("frame_index", "")).isdigit()}
                for order_i, f_idx in enumerate(f_indices):
                    img_p = f_images[order_i] if order_i < len(f_images) else None
                    pk = pk_by_idx.get(int(f_idx)) or (per_kf[order_i] if order_i < len(per_kf) and isinstance(per_kf[order_i], dict) else {})
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO sign_keyframes (
                            lesson_id, frame_order, frame_index, timestamp_s, image_path,
                            vlm_handshape, vlm_handshape_el,
                            vlm_placement, vlm_placement_el,
                            vlm_mouth_face, vlm_mouth_face_el,
                            vlm_notes, vlm_notes_el
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            lid,
                            order_i + 1,
                            int(f_idx),
                            round(int(f_idx) / fps, 2) if fps else 0.0,
                            img_p,
                            pk.get("handshape"),
                            pk.get("handshape_el"),
                            pk.get("hand_placement"),
                            pk.get("hand_placement_el"),
                            pk.get("mouth_and_face"),
                            pk.get("mouth_and_face_el"),
                            pk.get("posture_notes"),
                            pk.get("posture_notes_el"),
                        ),
                    )
            conn.commit()

    return len(signs)


def get_all_titles(db_path: str = PRIMARY_DB_PATH) -> list[str]:
    if not os.path.exists(db_path):
        return []
    with get_sqlite_conn(db_path) as conn:
        rows = conn.execute("SELECT title FROM sign_lessons ORDER BY seq_order").fetchall()
        return [r["title"] for r in rows]


def get_lesson(lesson_id: int | None = None, title: str | None = None, db_path: str = PRIMARY_DB_PATH) -> dict | None:
    """Retrieve a single lesson and its keyframes by lesson_id or title."""
    if not os.path.exists(db_path):
        return None
    with get_sqlite_conn(db_path) as conn:
        row = None
        if lesson_id is not None:
            row = conn.execute("SELECT * FROM sign_lessons WHERE lesson_id = ?", (int(lesson_id),)).fetchone()
        if not row and title:
            row = conn.execute("SELECT * FROM sign_lessons WHERE title = ?", (title,)).fetchone()
            if not row:
                t_norm = _norm(title)
                for candidate in conn.execute("SELECT * FROM sign_lessons").fetchall():
                    if _norm(candidate["title"]) == t_norm:
                        row = candidate
                        break
        if not row:
            return None
        d = dict(row)
        kfs = conn.execute(
            "SELECT * FROM sign_keyframes WHERE lesson_id = ? ORDER BY frame_order",
            (d["lesson_id"],),
        ).fetchall()
        d["keyframes"] = [dict(k) for k in kfs]
        return d


def get_next_lesson(current_lesson_id: int | None = None, current_title: str | None = None, db_path: str = PRIMARY_DB_PATH) -> dict | None:
    """
    Given a current lesson_id or title, returns the next lesson in the curriculum order
    (or the first lesson if none specified).
    """
    if not os.path.exists(db_path):
        return None
    cur = get_lesson(lesson_id=current_lesson_id, title=current_title, db_path=db_path)
    with get_sqlite_conn(db_path) as conn:
        if cur:
            nxt = conn.execute(
                "SELECT lesson_id FROM sign_lessons WHERE seq_order > ? ORDER BY seq_order ASC LIMIT 1",
                (cur["seq_order"],),
            ).fetchone()
            if nxt:
                return get_lesson(lesson_id=nxt["lesson_id"], db_path=db_path)
        first = conn.execute("SELECT lesson_id FROM sign_lessons ORDER BY seq_order ASC LIMIT 1").fetchone()
        return get_lesson(lesson_id=first["lesson_id"], db_path=db_path) if first else None


def retrieve_from_db(question: str, k: int = 3, next_lesson_hint: dict | None = None, db_path: str = PRIMARY_DB_PATH) -> list[dict]:
    """
    Retrieve the top-k relevant sign_lessons rows from the database for a question:
      1. If `next_lesson_hint` (e.g. from /api/v1/coach or game state) is provided and the user asks
         about the next game/lesson, prioritize that lesson.
      2. Exact title or lesson ID match in the question.
      3. BM25 keyword scoring over `rag_chunk_text` stored in `sign_lessons`.
    """
    if not os.path.exists(db_path):
        sync_to_db()

    with get_sqlite_conn(db_path) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM sign_lessons ORDER BY seq_order").fetchall()]

    if not rows:
        return []

    q_norm = _norm(question)
    qn = " " + " ".join(_tokens(question)) + " "
    out = []

    if next_lesson_hint:
        hint_lesson = get_lesson(
            lesson_id=next_lesson_hint.get("lessonId"),
            title=next_lesson_hint.get("lessonTitle") or next_lesson_hint.get("title"),
            db_path=db_path,
        )
        if hint_lesson:
            out.append(hint_lesson)

    m_lid = re.search(r"\b(?:lesson|μαθημα|game|παιχνιδι)\s*#?(\d+)\b", q_norm)
    if m_lid:
        lid_match = get_lesson(lesson_id=int(m_lid.group(1)), db_path=db_path)
        if lid_match and all(x["lesson_id"] != lid_match["lesson_id"] for x in out):
            out.append(lid_match)

    exact = [r for r in rows if f" {' '.join(_tokens(r['title']))} " in qn]
    for r in sorted(exact, key=lambda c: -len(c["title"])):
        if len(out) >= k:
            break
        if all(x["lesson_id"] != r["lesson_id"] for x in out):
            out.append(r)

    if exact and any(w in q_norm for w in ("next", "after", "επομενο", "μετα")):
        nxt = get_next_lesson(current_lesson_id=exact[0]["lesson_id"], db_path=db_path)
        if nxt and all(x["lesson_id"] != nxt["lesson_id"] for x in out):
            out.insert(0, nxt)

    docs = [Counter(_tokens(r["rag_chunk_text"] or "")) for r in rows]
    N = len(docs)
    avg = sum(sum(d.values()) for d in docs) / max(1, N)
    df = Counter(t for d in docs for t in d)
    q_toks = _tokens(question)

    def bm25(d):
        L = sum(d.values())
        return sum(
            math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5)) * d[t] * 2.2 / (d[t] + 1.2 * (0.25 + 0.75 * L / max(1.0, avg)))
            for t in q_toks if t in d
        )

    ranked = sorted(range(N), key=lambda i: -bm25(docs[i]))
    for i in ranked:
        if len(out) >= k:
            break
        if all(x["lesson_id"] != rows[i]["lesson_id"] for x in out):
            out.append(rows[i])

    return out[:k]


if __name__ == "__main__":
    n = sync_to_db()
    print(f"💾 Synced {n} lessons and their keyframes into {PRIMARY_DB_PATH} and {ROOT_DB_PATH}")
