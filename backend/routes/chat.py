from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json
import time

# Backend imports
from backend import database, llm_service, platform_connector, rag_engine
from backend.logging_config import logger
from backend.rate_limiter import rate_limiter

router = APIRouter()

# --- CONTEXT CACHE ---
user_context_cache = {}
CACHE_TTL = 300

import os

PROMPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "prompt.txt"))

DEFAULT_SYSTEM_PROMPT = """You are a VISTA-SL AI Coach. 
You help students learn Greek Sign Language. 

CONTEXT:
1. Use the provided STUDENT PROFILE to see their progress (number of lessons completed, recently studied lessons, and recommended next lesson).
2. Recommend the next logical lessons or units based on what they have already completed, keeping the learning sequence in mind.
3. Use the provided AVAILABLE CURRICULUM outline to understand the overall learning progression.
4. Do not write or include video URLs yourself.
5. At the end of your response, make a "RECOMMEND:" section with the exact Greek title of the next lesson the user needs to take (e.g., "RECOMMEND: Αγόρι").
6. Keep answers concise and direct.

IDENTITY: You are a direct, encouraging tutor. You MUST ALWAYS respond in Greek (Ελληνικά), regardless of the language the user uses to chat."""

def get_system_prompt() -> str:
    if os.path.exists(PROMPT_PATH):
        try:
            with open(PROMPT_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"⚠️ Error reading prompt.txt: {e}")
    return DEFAULT_SYSTEM_PROMPT

def find_recommended_lesson(text: str) -> list[dict]:
    """
    Finds the lesson title recommended in the 'RECOMMEND:' section of the text
    and returns its matching lesson dictionary if found.
    """
    import re
    import unicodedata
    
    def normalize_greek(s: str) -> str:
        s = s.lower().strip()
        decomposed = unicodedata.normalize('NFKD', s)
        stripped = "".join([c for c in decomposed if not unicodedata.combining(c)])
        return stripped.strip('.,;!?()"\'-*')

    def is_word_in_text(word: str, text: str) -> bool:
        if word not in text:
            return False
        idx = text.index(word)
        if idx > 0 and text[idx - 1].isalpha():
            return False
        end_idx = idx + len(word)
        if end_idx < len(text) and text[end_idx].isalpha():
            return False
        return True

    match = re.search(r"RECOMMEND:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not match:
        return []
    
    rec_title = match.group(1).strip()
    norm_rec = normalize_greek(rec_title)
    if not norm_rec:
        return []
        
    all_lessons = []
    for mod, lessons in rag_engine._modules.items():
        all_lessons.extend(lessons)
    # Sort by title length descending to match longest titles first
    all_lessons.sort(key=lambda x: len(x.get('title', '')), reverse=True)
    
    # Try normalized exact match first
    for lesson in all_lessons:
        title = lesson.get('title', '')
        if normalize_greek(title) == norm_rec:
            return [lesson]
            
    # Fallback 1: normalized word-boundary substring match
    for lesson in all_lessons:
        title = lesson.get('title', '')
        norm_title = normalize_greek(title)
        if norm_title and is_word_in_text(norm_title, norm_rec):
            return [lesson]
            
    # Fallback 2: stem prefix matching (handles Greek noun declensions e.g. Γάτα -> Γάτος)
    for lesson in all_lessons:
        title = lesson.get('title', '')
        norm_title = normalize_greek(title)
        if len(norm_title) >= 3:
            # Strip last 1 or 2 characters to get the word stem
            stem_len = len(norm_title) - (2 if len(norm_title) > 4 else 1)
            stem = norm_title[:stem_len]
            # Check if any word in the recommended title starts with this stem
            if any(w.startswith(stem) for w in norm_rec.split()):
                return [lesson]
            
    return []

class ChatRequest(BaseModel):
    userId: str
    token: str
    message: str

@router.post("/chat")
async def chat_endpoint(request: ChatRequest, debug: bool = False, db: Session = Depends(database.get_db)):
    # 0. Check Rate Limiter
    if rate_limiter.is_rate_limited(request.userId):
        logger.warning(f"Rate limit triggered for user: {request.userId}")
        raise HTTPException(status_code=429, detail="Too Many Requests. Rate limit exceeded.")

    # 1. Load History (Small window for efficiency)
    history = database.get_recent_messages(db, request.userId, limit=5)

    # 2. RAG Search (THIS SAVES 95% TOKENS)
    # Instead of whole curriculum, we only find the top 3 relevant items.
    rag_context = rag_engine.search_curriculum(request.message, top_k=3)

    # 3. User Progress
    now = time.time()
    if request.userId in user_context_cache and (now < user_context_cache[request.userId]["expiry"]):
        user_stats = user_context_cache[request.userId]["stats"]
    else:
        try:
            user_stats = await platform_connector.fetch_user_progress(request.userId, request.token)
            user_context_cache[request.userId] = {"stats": user_stats, "expiry": now + CACHE_TTL}
        except Exception as e:
            logger.error(f"Failed to fetch user progress: {e}")
            user_stats = "No progress data available."

    # 4. Construct Prompt
    # Build a compact curriculum outline dynamically to save tokens
    all_modules = rag_engine.get_module_list()
    curriculum_outline = "CURRICULUM TOPICS: " + " | ".join(all_modules)

    system_prompt = get_system_prompt()
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n{curriculum_outline}\n\nSTUDENT PROFILE:\n{user_stats}\n\n{rag_context}"}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": request.message})

    # Log incoming chat details
    logger.info(f"Chat request received: user_id={request.userId}, message='{request.message[:50]}...'")
    if debug:
        logger.debug(f"User ID: {request.userId}")
        logger.debug(f"Loaded Chat History: {json.dumps(history, ensure_ascii=False)}")
        logger.debug(f"RAG Context: {rag_context}")
        logger.debug(f"User Stats: {user_stats}")
        logger.debug(f"Constructed Messages: {json.dumps(messages, ensure_ascii=False)}")

    # 5. Save and Stream
    database.save_message(db, request.userId, "user", request.message)

    async def response_generator():
        full_response = []
        async for chunk in llm_service.stream_chat(messages):
            full_response.append(chunk)
            yield f"data: {json.dumps({'token': chunk})}\n\n"
        
        # Scrape full response text for the recommended lesson title and append its URL
        response_text = "".join(full_response)
        matches = find_recommended_lesson(response_text)
        if matches:
            links_text = "\n\n🎥 **Video References:**\n"
            for m in matches:
                links_text += f"- [{m.get('title')}]({m.get('link')})\n"
            yield f"data: {json.dumps({'token': links_text})}\n\n"
            full_response.append(links_text)

        yield "data: [DONE]\n\n"
        full_resp_str = "".join(full_response)
        
        if debug:
            logger.debug(f"Assistant Response: {full_resp_str}")
            
        if full_response:
            database.save_message(db, request.userId, "assistant", full_resp_str)

    return StreamingResponse(response_generator(), media_type="text/event-stream")

@router.post("/chat/clear")
async def clear_chat_history(request: dict, db: Session = Depends(database.get_db)):
    user_id = request.get("userId")
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing userId")
    database.clear_history(db, user_id)
    if user_id in user_context_cache:
        del user_context_cache[user_id]
    logger.info(f"Cleared history and context cache for user: {user_id}")
    return {"status": "success", "message": f"History cleared for user {user_id}"}
