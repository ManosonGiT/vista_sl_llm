import json
import os
import sys
import time

# Import our modular helpers
import llm_service
from database import db_manager
import platform_connector  # <--- NEW IMPORT

# Config
SIMULATION_FILE = "frontend_simulate_key.json"

def run_simulation(user_key="user_1"):
    # 1. Load User Credentials
    if not os.path.exists(SIMULATION_FILE):
        print(f"❌ {SIMULATION_FILE} missing.")
        return

    with open(SIMULATION_FILE, 'r') as f:
        users = json.load(f)
        current_user = users.get(user_key)
    
    if not current_user:
        print(f"❌ User key '{user_key}' not found in JSON.")
        return

    user_id = current_user['userId']
    user_token = current_user['token']
    
    print(f"\n🔑 LOGGED IN AS: {current_user['username']} ({user_id})")
    
    # 2. RAG: Fetch Platform Data
    print("-" * 50)
    print("🧠 RAG SYSTEM: Gathering Context...")
    rag_context = platform_connector.get_rag_context(user_token)
    print("✅ Context Loaded into Memory.")
    print("-" * 50)

    # 3. Initialize DB & Get Thread
    db_manager.init_db()
    slug = db_manager.get_thread_slug(user_id)
    
    if slug:
        print(f"📂 Found existing thread: {slug}")
    else:
        print("🆕 First time user! Creating new thread...")
        slug = llm_service.create_thread(user_id)
        if slug:
            db_manager.save_thread_slug(user_id, slug)
            print(f"✅ Created and Saved Thread: {slug}")
        else:
            print("❌ Failed to create thread.")
            return

    # 4. SHOW CONTEXT (Chat History)
    print("\n" + "="*50)
    print("📜 CHAT HISTORY")
    print("="*50)
    
    history = llm_service.fetch_chat_history(slug)
    if not history:
        print("(No previous messages)")
    else:
        for msg in history:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content') or msg.get('message')
            print(f"[{role}]: {content}")
    
    print("="*50 + "\n")

    # 5. SEND NEW MESSAGE
    try:
        user_input = input("💬 Enter your message: ")
    except KeyboardInterrupt:
        print("\n👋 Exiting.")
        return
    
    # --- INJECT RAG CONTEXT ---
    # We prepend the RAG context to the user's message invisibly.
    # The AI sees the context, but the user only typed "Help me".
    final_prompt = f"{rag_context}\n\nUSER MESSAGE:\n{user_input}"
    
    print("\n🤖 Assistant is typing...", end="", flush=True)
    print("\r" + " "*30 + "\r🤖 Assistant: ", end="", flush=True)

    # 6. STREAM RESPONSE
    token_count = 0
    # Note: We send 'final_prompt' to the LLM, but the user feels like they sent 'user_input'
    for chunk in llm_service.stream_chat(slug, final_prompt):
        token_count += 1
        sys.stdout.write(chunk)
        sys.stdout.flush()

    if token_count == 0:
        print("(No response received. Check API logs.)")
    
    print("\n" + "-"*50)
    print("✅ Interaction Complete.")

if __name__ == "__main__":
    selected_user = sys.argv[1] if len(sys.argv) > 1 else "user_1"
    run_simulation(selected_user)