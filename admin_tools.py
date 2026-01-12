import asyncio
import sys
import os
import requests
import database
from sqlalchemy.orm import Session
import llm_service
from dotenv import load_dotenv

load_dotenv()
database.init_db()

def get_db_session():
    return database.SessionLocal()

# --- COMMAND 1: LIST USERS ---
def list_users():
    db = get_db_session()
    users = db.query(database.UserThread).all()
    db.close()
    print(f"\n📊 FOUND {len(users)} USERS IN DATABASE")
    print(f"{'USER ID':<25} | {'THREAD SLUG':<40}")
    print("-" * 70)
    for user in users:
        print(f"{user.user_id:<25} | {user.thread_slug:<40}")
    print("-" * 70 + "\n")

# --- COMMAND 2: DELETE USER ---
async def delete_user_history(user_id: str):
    db = get_db_session()
    user = db.query(database.UserThread).filter(database.UserThread.user_id == user_id).first()
    
    if not user:
        print(f"❌ User '{user_id}' not found.")
        db.close()
        return

    print(f"🔍 Found Thread: {user.thread_slug}")
    print("   🧠 Deleting from AnythingLLM...", end=" ")
    await llm_service.delete_thread(user.thread_slug)
    print("✅ Success")

    print("   🗑️  Deleting from Database...", end=" ")
    db.delete(user)
    db.commit()
    db.close()
    print("✅ Success")

# --- COMMAND 3: WIPE LOGS (Using the -1 Trick) ---
def wipe_system_logs():
    base_url = os.getenv("ANYTHING_LLM_URL")
    api_key = os.getenv("anything_llm_cookie")
    
    # 🎯 The exact endpoint from your screenshot
    url = f"{base_url}/api/system/workspace-chats/-1"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    print(f"\n☢️  ATTEMPTING SYSTEM LOG WIPE (Target: -1)")
    print(f"   URL: {url}")
    
    try:
        resp = requests.delete(url, headers=headers)
        
        if resp.status_code == 200:
            print("✅ SUCCESS! The system accepted the -1 command.")
            print("   Visual logs should now be empty.")
        elif resp.status_code == 403 or resp.status_code == 401:
            print(f"❌ Permission Denied ({resp.status_code}).")
            print("   Reason: This endpoint requires a 'Human Admin Token' (JWT), not a Developer API Key.")
            print("   👉 Solution: You must click the 'Clear Chats' button in the browser.")
        else:
            print(f"❌ Failed: {resp.status_code} - {resp.text}")

    except Exception as e:
        print(f"💥 Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python admin_tools.py [list | delete <id> | wipe_logs]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        list_users()
    elif command == "delete":
        asyncio.run(delete_user_history(sys.argv[2]))
    elif command == "wipe_logs":
        wipe_system_logs()