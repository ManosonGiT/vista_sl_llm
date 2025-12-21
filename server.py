from flask import Flask, request, Response, stream_with_context
from flask_cors import CORS
import json
import sys

# Import our helper modules
import llm_service
import platform_connector
from database import db_manager

app = Flask(__name__)
CORS(app) # Allow connections from browsers

@app.route('/chat', methods=['POST'])
def chat_endpoint():
    """
    Main entry point. Receives User ID, Token, and Message.
    Orchestrates RAG, DB, and LLM. Returns SSE Stream.
    """
    data = request.json
    user_id = data.get('userId')
    user_token = data.get('token')
    message = data.get('message')

    print(f"\n📩 Incoming Request from: {user_id}")

    # 1. Initialize DB & Get Thread Slug
    db_manager.init_db()
    slug = db_manager.get_thread_slug(user_id)
    
    if not slug:
        print(f"   🆕 Creating new thread for {user_id}...")
        slug = llm_service.create_thread(user_id)
        if slug:
            db_manager.save_thread_slug(user_id, slug)
        else:
            return {"error": "Failed to create thread"}, 500
    else:
        print(f"   📂 Using existing thread: {slug}")

    # 2. RAG Context Injection
    # We fetch this on the server side so the client doesn't need to know logic
    print("   🧠 Fetching RAG Context...")
    rag_context = platform_connector.get_rag_context(user_token)
    
    # 3. Construct Final Prompt
    final_prompt = f"{rag_context}\n\nUSER MESSAGE:\n{message}"

    # 4. Stream Response (SSE Format)
    def generate():
        # Standard SSE format: "data: <content>\n\n"
        for chunk in llm_service.stream_chat(slug, final_prompt):
            # Wrap in JSON so the frontend can easily parse it
            payload = json.dumps({"token": chunk})
            yield f"data: {payload}\n\n"
        
        # Signal end of stream
        yield "data: [DONE]\n\n"

    print("   🚀 Streaming response to client...")
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

if __name__ == '__main__':
    print("==========================================")
    print("🌍 SERVER RUNNING ON http://localhost:5000")
    print("==========================================")
    app.run(port=5000, debug=True)