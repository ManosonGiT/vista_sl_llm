from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

# Local modules
import database
import llm_service
import platform_connector

app = FastAPI(title="VISTA-SL LLM Backend")

# 1. Initialize DB on Startup
@app.on_event("startup")
def startup_event():
    print("🔄 Application Starting: Initializing Database...")
    database.init_db()
    print("✅ Database Ready.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    userId: str
    token: str
    message: str

@app.post("/chat")
async def chat_endpoint(request: ChatRequest, db: Session = Depends(database.get_db)):
    print(f"📩 Request from: {request.userId}")

    # A. Thread Management
    slug = database.get_thread_slug(db, request.userId)
    
    if not slug:
        print("   🆕 Creating new thread...")
        slug = await llm_service.create_thread(request.userId)
        if not slug:
            raise HTTPException(status_code=500, detail="Failed to create thread")
        database.save_thread_slug(db, request.userId, slug)
    else:
        print(f"   📂 Using existing thread: {slug}")
    
    # B. RAG Context
    print("   🧠 Fetching Context...")
    try:
        user_stats = await platform_connector.fetch_user_progress(request.token)
    except Exception as e:
        print(f"❌ Platform Connector Failed: {e}")
        user_stats = "Error fetching stats."
    final_prompt = f"SYSTEM INJECTION:\n{user_stats}\n\nUSER MESSAGE:\n{request.message}"

    # C. Stream Response
    async def response_generator():
        # Track if we actually got data
        has_data = False
        
        try:
            async for chunk in llm_service.stream_chat(slug, final_prompt):
                # 🛠️ CHECK FOR 404 OR ERROR
                if "404" in chunk or "Thread not found" in chunk or "Error" in chunk:
                    print(f"   🚨 Critical Mismatch: Thread {slug} is dead.")
                    
                    # 1. Delete the bad record from YOUR database
                    try:
                        # (You need to add a simple delete function to database.py)
                        db.query(database.UserThread).filter(database.UserThread.user_id == request.userId).delete()
                        db.commit()
                        print("   🧹 Deleted stale user record. Next request will generate a new thread.")
                    except:
                        pass
                        
                    yield f"data: {json.dumps({'token': ' [System: Connection reset. Please try again.]'})}\n\n"
                    return

                has_data = True
                data = json.dumps({"token": chunk})
                yield f"data: {data}\n\n"
            
            if not has_data:
                yield f"data: {json.dumps({'token': ' [System: Error. No response from AI.]'})}\n\n"
                
            yield "data: [DONE]\n\n"

        except Exception as e:
            print(f"💥 Stream Error: {e}")

    return StreamingResponse(response_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)