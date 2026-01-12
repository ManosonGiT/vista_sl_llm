import sqlite3
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
# Use os.path.join and ".." to safely navigate to the parent directory
DB_FILE = os.path.join("..", "bot_database.db") 

BASE_URL = "https://vistachatbot.hmu.gr"
WORKSPACE_SLUG = "vista-sl_temp"
ANYTHING_LLM_KEY = os.getenv("ANYTHING_LLM_KEY")

def load_api_key():
    if not ANYTHING_LLM_KEY:
        print("❌ Error: ANYTHING_LLM_KEY not found in environment.")
        return None
    
    raw_key = ANYTHING_LLM_KEY.strip()
    return raw_key if raw_key.startswith("Bearer ") else f"Bearer {raw_key}"

def get_db_users():
    """Reads all users and slugs from the local SQLite DB in the parent directory."""
    # Resolve the absolute path for debugging clarity
    abs_path = os.path.abspath(DB_FILE)
    
    if not os.path.exists(abs_path):
        print(f"❌ Error: Database file not found at: {abs_path}")
        return []
    
    conn = sqlite3.connect(abs_path)
    c = conn.cursor()
    try:
        c.execute("SELECT user_id, thread_slug FROM user_threads")
        return c.fetchall()
    except sqlite3.OperationalError as e:
        print(f"❌ Database Error: {e}")
        return []
    finally:
        conn.close()

def fetch_thread_history(slug, api_key):
    """Downloads chat logs for a specific slug."""
    url = f"{BASE_URL.rstrip('/')}/api/v1/workspace/{WORKSPACE_SLUG}/thread/{slug}/chats"
    headers = {"Authorization": api_key}
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Handle both list responses and dictionary responses containing 'history'
            return data.get('history') if isinstance(data, dict) else data
        else:
            print(f"    ⚠️  API Error {resp.status_code} for slug {slug}")
            return []
    except Exception as e:
        print(f"    ⚠️  Request failed: {e}")
        return []

def run_audit():
    api_key = load_api_key()
    if not api_key: 
        return

    users = get_db_users()
    if not users:
        print("ℹ️ No user data available to audit.")
        return

    print(f"\n📊 AUDIT REPORT: Found {len(users)} tracked users.")
    print("="*60)

    for user_id, slug in users:
        print(f"👤 USER: {user_id}")
        print(f"🆔 THREAD SLUG: {slug}")
        
        history = fetch_thread_history(slug, api_key)
        
        if not history or not isinstance(history, list):
            print("   (No messages in history yet)")
        else:
            print("   📜 RECENT HISTORY:")
            # Display last 3 interactions
            for msg in history[-3:]: 
                role = msg.get('role', 'unknown').upper()
                text = msg.get('content') or msg.get('message') or ""
                preview = (text[:75].replace('\n', ' ') + '..') if len(text) > 75 else text.replace('\n', ' ')
                print(f"      [{role}]: {preview}")
        
        print("-" * 60)

if __name__ == "__main__":
    run_audit()