from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json
import time

# Backend imports
from backend import database, llm_service, platform_connector, rag_engine

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

def find_mentioned_lessons(text: str) -> list[dict]:
    """
    Scans the response text for exact Greek curriculum lesson titles.
    Filters out subset matches for short lesson titles (e.g. single Greek characters).
    """
    import re
    matched = []
    all_lessons = []
    for mod, lessons in rag_engine._modules.items():
        all_lessons.extend(lessons)
        
    # Sort lessons by title length descending to match multi-word signs first
    all_lessons.sort(key=lambda x: len(x.get('title', '')), reverse=True)
    
    text_lower = text.lower()
    used_titles = set()
    
    for lesson in all_lessons:
        title = lesson.get('title', '')
        if not title:
            continue
        title_lower = title.lower()
        
        if title_lower in used_titles:
            continue
            
        if title_lower in text_lower:
            # Standalone word validation for single character signs
            if len(title) <= 2:
                pattern = r'(?:\s|^|[.,;!?()"\'-])' + re.escape(title_lower) + r'(?:\s|$|[.,;!?()"\'-])'
                if not re.search(pattern, text_lower):
                    continue
            
            matched.append(lesson)
            used_titles.add(title_lower)
            
    return matched

class ChatRequest(BaseModel):
    userId: str
    token: str
    message: str

@router.post("/chat")
async def chat_endpoint(request: ChatRequest, debug: bool = False, db: Session = Depends(database.get_db)):
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
            user_stats = await platform_connector.fetch_user_progress(request.userId)
            user_context_cache[request.userId] = {"stats": user_stats, "expiry": now + CACHE_TTL}
        except:
            user_stats = "No progress data available."

    # 4. Construct Prompt
    # Build a compact curriculum outline dynamically to save tokens
    all_modules = rag_engine.get_module_list()
    curriculum_summaries = []
    for mod in all_modules:
        lessons = rag_engine._modules.get(mod, [])
        titles = [l.get('title') for l in lessons[:4]]
        curriculum_summaries.append(f"- {mod} (Lessons include: {', '.join(titles)}...)")
    curriculum_outline = "AVAILABLE CURRICULUM:\n" + "\n".join(curriculum_summaries)

    system_prompt = get_system_prompt()
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n{curriculum_outline}\n\nSTUDENT PROFILE:\n{user_stats}\n\n{rag_context}"}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": request.message})

    if debug:
        print("\n🔍 === DEBUG CHAT START ===")
        print(f"👤 User ID: {request.userId}")
        print(f"💬 User Message: {request.message}")
        print("📜 --- Loaded Chat History ---")
        print(json.dumps(history, indent=2, ensure_ascii=False))
        print("📚 --- RAG Context ---")
        print(rag_context)
        print("📈 --- User Stats ---")
        print(user_stats)
        print("🧠 --- Constructed Messages to Send to LLM ---")
        print(json.dumps(messages, indent=2, ensure_ascii=False))
        print("========================\n")

    # 5. Save and Stream
    database.save_message(db, request.userId, "user", request.message)

    async def response_generator():
        full_response = []
        async for chunk in llm_service.stream_chat(messages):
            full_response.append(chunk)
            yield f"data: {json.dumps({'token': chunk})}\n\n"
        
        # Scrape full response text for mentioned lesson titles and append URLs dynamically
        response_text = "".join(full_response)
        matches = find_mentioned_lessons(response_text)
        if matches:
            links_text = "\n\n🎥 **Video References:**\n"
            for m in matches:
                links_text += f"- [{m.get('title')}]({m.get('link')})\n"
            yield f"data: {json.dumps({'token': links_text})}\n\n"
            full_response.append(links_text)

        yield "data: [DONE]\n\n"
        full_resp_str = "".join(full_response)
        
        if debug:
            print("\n🤖 === DEBUG CHAT RESPONSE ===")
            print(f"Assistant Response: {full_resp_str}")
            print("===========================\n")
            
        if full_response:
            database.save_message(db, request.userId, "assistant", full_resp_str)

    return StreamingResponse(response_generator(), media_type="text/event-stream")
