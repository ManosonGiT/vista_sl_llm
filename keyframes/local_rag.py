"""
Database-backed RAG & Next-Game Coach over the VISTA-SL signing knowledge base,
protected by Sign-Language-Only topic guardrails.

Usage:
  # 1. Sync cache.json + enriched.json into the database & build KB files:
  venv/bin/python -m keyframes.local_rag --build

  # 2. Ask a general sign language question (in Greek, English, or any language):
  venv/bin/python -m keyframes.local_rag "Πώς κάνω το Αγόρι;"
  venv/bin/python -m keyframes.local_rag "How do I sign Αγόρι?"

  # 3. Retrieve & explain a specific game / lesson (or the next lesson after a given one):
  venv/bin/python -m keyframes.local_rag --lesson "Αγόρι"
  venv/bin/python -m keyframes.local_rag --after 11
"""
import os
import re
import sys
import json
import argparse

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keyframes.db_store import (  # noqa: E402
    sync_to_db,
    get_all_titles,
    get_lesson,
    get_next_lesson,
    retrieve_from_db,
    format_row_for_prompt,
)
from keyframes.guardrails import (  # noqa: E402
    check_question_allowed,
    GUARDRAIL_SYSTEM_INSTRUCTION,
)

load_dotenv()
LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:9001").rstrip("/")
LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "google/gemma-4-E4B-it")
PLATFORM_URL = os.getenv("PLATFORM_URL", "https://vistasl.eelvex.net").rstrip("/")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KB_FILE = os.path.join(ROOT, "signing_knowledge_base.txt")
INDEX_FILE = os.path.join(HERE, "rag_index.json")


def _active_model() -> str:
    try:
        r = httpx.get(f"{LLM_URL}/v1/models", timeout=2.0)
        if r.status_code == 200:
            data = r.json().get("data") or []
            if data and data[0].get("id"):
                return data[0]["id"]
    except Exception:
        pass
    return LLM_MODEL


def detect_question_lang(question: str) -> str:
    """
    Detect whether the user's question is written primarily in Greek ('el') or English/other ('en').
    Even if an English question quotes a Greek sign title (e.g., "How do I sign Αγόρι?"),
    the presence of English question words classifies the question language as 'en'.
    """
    q = question or ""
    latin_letters = len(re.findall(r"[A-Za-z]", q))
    greek_letters = len(re.findall(r"[\u0370-\u03ff\u1f00-\u1fff]", q))
    en_markers = re.search(
        r"\b(how|what|where|when|why|which|who|can|could|should|do|does|is|are|sign|make|perform|show|tell|explain|next|lesson|game)\b",
        q.lower(),
    )
    if en_markers or latin_letters > greek_letters:
        return "en"
    if greek_letters > 0:
        return "el"
    return "en"


SYSTEM_EN = f"""You are the VISTA-SL Virtual Instructor for Greek Sign Language (GSL / Ελληνική Νοηματική Γλώσσα).
{GUARDRAIL_SYSTEM_INSTRUCTION}

RESPONSE RULES:
1. Answer using ONLY the CONTEXT entries retrieved from the database.
2. NEVER mention "keyframes", frame numbers (e.g. "frame 40"), or timestamps (e.g. "1.33s") in your answer. Explain the sign naturally and smoothly as a human sign-language teacher.
3. Always refer to the signing hand as the "dominant hand" (never left/right hand).
4. Include:
   - Lesson title and link
   - How to sign it (handshape, palm orientation, placement on face/body, mouthing & facial expression, movement)
   - Important factors to get right
   - Step-by-step instructions and the reference video URL
5. Do NOT include a "Common mistakes" section.
6. LANGUAGE RULE: You MUST write your ENTIRE response in the EXACT same language that the user used to ask the question."""

SYSTEM_EL = f"""Είσαι ο Εικονικός Εκπαιδευτής του VISTA-SL για την Ελληνική Νοηματική Γλώσσα (ΕΝΓ).
{GUARDRAIL_SYSTEM_INSTRUCTION}

ΚΑΝΟΝΕΣ ΑΠΑΝΤΗΣΗΣ:
1. Απάντησε χρησιμοποιώντας ΑΠΟΚΛΕΙΣΤΙΚΑ τις πληροφορίες από το CONTEXT της βάσης δεδομένων.
2. ΠΟΤΕ μην αναφέρεις τις λέξεις "keyframe", "καρέ", αριθμούς καρέ (π.χ. "frame 40") ή δευτερόλεπτα (π.χ. "1.33s") στην απάντησή σου. Εξήγησε το νόημα φυσικά, όπως ένας δάσκαλος νοηματικής.
3. Χρησιμοποίησε πάντα τον όρο "κυρίαρχο χέρι" (όχι δεξί/αριστερό χέρι).
4. Συμπερίλαβε:
   - Τον τίτλο και τον σύνδεσμο του μαθήματος
   - Πώς εκτελείται το νόημα (σχήμα χεριού, προσανατολισμός παλάμης, τοποθέτηση στο πρόσωπο/σώμα, προφορική άρθρωση & έκφραση προσώπου, κίνηση)
   - Τους σημαντικούς παράγοντες επιτυχίας
   - Οδηγίες βήμα-βήμα και το βίντεο αναφοράς
5. ΜΗΝ συμπεριλάβεις ενότητα για "Συνηθισμένα λάθη".
6. ΚΑΝΟΝΑΣ ΓΛΩΣΣΑΣ: Η ερώτηση του χρήστη είναι στα Ελληνικά, επομένως ΠΡΕΠΕΙ να απαντήσεις ΑΠΟΚΛΕΙΣΤΙΚΑ στα ΕΛΛΗΝΙΚΑ."""


def build():
    """Sync all lessons & keyframes into SQLite DB and export rag_index.json + signing_knowledge_base.txt."""
    n = sync_to_db()
    rows = retrieve_from_db("sign", k=500)
    rows.sort(key=lambda r: r.get("seq_order") or 0)
    chunks = [{"lesson_id": r["lesson_id"], "title": r["title"], "text": r["rag_chunk_text"]} for r in rows]
    json.dump(chunks, open(INDEX_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(KB_FILE, "w", encoding="utf-8") as f:
        f.write("VISTA-SL SIGNING GUIDE (Database-backed signing descriptions)\n\n")
        f.write("\n---\n".join(c["text"] for c in chunks) + "\n")
    print(f"🗄️  Synced {n} lessons to database\n📚 Indexed {len(chunks)} chunks -> {INDEX_FILE}\n📝 Wrote {KB_FILE}")


def retrieve(question: str, k: int = 3, next_lesson_hint: dict | None = None, lang: str | None = None) -> list[dict]:
    q_lang = lang or detect_question_lang(question)
    rows = retrieve_from_db(question, k=k, next_lesson_hint=next_lesson_hint)
    return [
        {
            "lesson_id": r["lesson_id"],
            "title": r["title"],
            "text": format_row_for_prompt(r, lang=q_lang),
            "row": r,
        }
        for r in rows
    ]


def ask(question: str, k: int = 3, next_lesson_hint: dict | None = None, show_context: bool = True) -> str:
    # 1. Sign-Language-Only Topic Guardrail check
    known_titles = get_all_titles()
    allowed, refusal = check_question_allowed(question, known_titles=known_titles)
    if not allowed:
        if show_context:
            print("🛡️  Guardrail blocked off-topic/unsafe query.")
        return refusal

    # 2. Detect question language & retrieve clean context (no keyframe numbers) in that language
    q_lang = detect_question_lang(question)
    ctx = retrieve(question, k=k, next_lesson_hint=next_lesson_hint, lang=q_lang)
    context = "\n\n---\n\n".join(c["text"] for c in ctx)
    if show_context:
        print(f"🔎 Retrieved from DB (lang={q_lang}):", [f"[{c['lesson_id']}] {c['title']}" for c in ctx])

    sys_prompt = SYSTEM_EL if q_lang == "el" else SYSTEM_EN
    lang_directive = (
        "Απάντησε ΑΠΟΚΛΕΙΣΤΙΚΑ στα Ελληνικά, χωρίς καμία αναφορά σε καρέ/keyframes και χωρίς ενότητα για συνηθισμένα λάθη."
        if q_lang == "el"
        else "IMPORTANT: Write your ENTIRE response in ENGLISH (only keep the sign title itself in quotes). Do NOT mention keyframes/frame numbers and do NOT include common mistakes."
    )

    # 3. Call LLM (with graceful offline fallback to DB knowledge if vLLM tunnel is down)
    try:
        r = httpx.post(
            f"{LLM_URL}/v1/chat/completions",
            timeout=120,
            json={
                "model": _active_model(),
                "temperature": 0.3,
                "max_tokens": 800,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\n({lang_directive})"},
                ],
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return (
            f"⚠️ (LLM endpoint {LLM_URL} unreachable: {e} — returning direct database records)\n\n"
            f"{context}"
        )


def ask_for_game(
    lesson_id: int | None = None,
    title: str | None = None,
    after_lesson_id: int | None = None,
    lang: str = "el",
) -> str:
    if after_lesson_id is not None:
        row = get_next_lesson(current_lesson_id=after_lesson_id)
    else:
        row = get_lesson(lesson_id=lesson_id, title=title)
    if not row:
        return "❌ Lesson not found in database."
    hint = {"lessonId": row["lesson_id"], "lessonTitle": row["title"]}
    if lang == "el":
        q = f"Πώς κάνω το νόημα '{row['title']}' (Μάθημα {row['lesson_id']}) για το επόμενο παιχνίδι εξάσκησης;"
    else:
        q = f"How do I perform the sign '{row['title']}' (Lesson {row['lesson_id']}) for the practice game?"
    return ask(q, k=1, next_lesson_hint=hint)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?")
    ap.add_argument("--build", action="store_true", help="Sync cache/enriched JSONs into SQLite DB and rebuild KB")
    ap.add_argument("--lesson", type=str, help="Retrieve & explain a specific lesson ID or sign title")
    ap.add_argument("--after", type=int, help="Retrieve & explain the next game/lesson after the given lessonId")
    ap.add_argument("--lang", type=str, default="el", choices=["el", "en"], help="Language for --lesson / --after")
    a = ap.parse_args()
    if a.build:
        build()
    if a.lesson:
        lid = int(a.lesson) if a.lesson.isdigit() else None
        print(ask_for_game(lesson_id=lid, title=None if lid else a.lesson, lang=a.lang))
    elif a.after is not None:
        print(ask_for_game(after_lesson_id=a.after, lang=a.lang))
    elif a.question:
        print(ask(a.question))
