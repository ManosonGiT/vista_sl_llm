from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

# Local modules
import database
import llm_service
import platform_connector
from keyframes.db_store import (
    init_db as init_keyframe_db,
    get_all_titles,
    get_lesson,
    get_next_lesson,
    retrieve_from_db,
    format_row_for_prompt,
)
from keyframes.local_rag import detect_question_lang
from keyframes.guardrails import (
    check_question_allowed,
    GUARDRAIL_SYSTEM_INSTRUCTION,
)

app = FastAPI(title="VISTA-SL LLM Backend")

# 1. Initialize DB on Startup
@app.on_event("startup")
def startup_event():
    print("🔄 Application Starting: Initializing Databases...")
    database.init_db()
    init_keyframe_db()
    print("✅ Databases Ready.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    userId: str
    token: str = ""
    message: str


@app.get("/keyframes/{id_or_title}")
async def get_lesson_keyframes(id_or_title: str):
    """Retrieve stored keyframe & VLM important factors for a specific lesson ID or title."""
    lid = int(id_or_title) if id_or_title.isdigit() else None
    row = get_lesson(lesson_id=lid, title=None if lid else id_or_title)
    if not row:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return row


@app.get("/next-game")
async def get_next_game_info(
    token: str = Query(default=""),
    current_lesson_id: int | None = Query(default=None),
):
    """Retrieve the next recommended game/lesson and its keyframe VLM factors from the database."""
    next_hint = None
    if token:
        _, next_hint = await platform_connector.fetch_user_progress_with_next(token)
    if next_hint:
        row = get_lesson(lesson_id=next_hint.get("lessonId"), title=next_hint.get("lessonTitle"))
        if row:
            return {"source": "platform_coach", "lesson": row}
    row = get_next_lesson(current_lesson_id=current_lesson_id)
    if not row:
        raise HTTPException(status_code=404, detail="No next lesson found")
    return {"source": "curriculum_sequence", "lesson": row}


@app.post("/chat")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(database.get_db)):
    print(f"📩 Request from: {request.userId}")

    # A. Sign-Language-Only Topic Guardrail
    known_titles = get_all_titles()
    allowed, refusal_msg = check_question_allowed(request.message, known_titles=known_titles)
    if not allowed:
        print("   🛡️ Blocked off-topic / unsafe message via Guardrail.")
        async def blocked_generator():
            yield f"data: {json.dumps({'token': refusal_msg})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(blocked_generator(), media_type="text/event-stream")

    # B. Thread Management
    slug = database.get_thread_slug(db, request.userId)
    if not slug:
        print("   🆕 Creating new thread...")
        slug = await llm_service.create_thread(request.userId)
        if not slug:
            raise HTTPException(status_code=500, detail="Failed to create thread")
        database.save_thread_slug(db, request.userId, slug)
    else:
        print(f"   📂 Using existing thread: {slug}")
    
    # C. RAG Context (Platform Progress + Database Signing Knowledge, no keyframe numbers)
    print("   🧠 Fetching Context & Signing Knowledge from DB...")
    q_lang = detect_question_lang(request.message)
    user_stats, next_lesson = await platform_connector.fetch_user_progress_with_next(request.token)
    db_matches = retrieve_from_db(request.message, k=3, next_lesson_hint=next_lesson)
    signing_context = "\n---\n".join(format_row_for_prompt(m, lang=q_lang) for m in db_matches)

    lang_rule = (
        "ΚΑΝΟΝΑΣ: Απάντησε ΑΠΟΚΛΕΙΣΤΙΚΑ στα ΕΛΛΗΝΙΚΑ. ΠΟΤΕ μην αναφέρεις τις λέξεις 'keyframe', 'καρέ', αριθμούς καρέ ή δευτερόλεπτα."
        if q_lang == "el"
        else "RULE: Reply in the EXACT same language as the USER MESSAGE. NEVER mention 'keyframes', frame numbers, or timestamps in your answer."
    )

    final_prompt = (
        f"SYSTEM GUARDRAIL:\n{GUARDRAIL_SYSTEM_INSTRUCTION}\n{lang_rule}\n\n"
        f"SYSTEM INJECTION (LEARNER PROGRESS):\n{user_stats}\n\n"
        f"DATABASE SIGNING KNOWLEDGE:\n{signing_context}\n\n"
        f"USER MESSAGE:\n{request.message}\n\n({lang_rule})"
    )

    # D. Stream Response
    async def response_generator():
        async for chunk in llm_service.stream_chat(slug, final_prompt):
            data = json.dumps({"token": chunk})
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(response_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
