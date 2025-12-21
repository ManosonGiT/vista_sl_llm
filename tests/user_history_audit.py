import sqlite3
import requests
import json
import os

# --- CONFIGURATION ---
DB_FILE = "bot_database.db"
BASE_URL = "https://vistachatbot.hmu.gr"
WORKSPACE_SLUG = "vista-sl_temp"
KEY_FILE = "api_keys/api_key.json"

def load_api_key():
    if not os.path.exists(KEY_FILE):
        print(f"❌ Error: {KEY_FILE} not found.")
        return None
    with open(KEY_FILE, 'r') as f:
        data = json.load(f)
        raw_key = data.get("api_key", "").strip()
        return f"Bearer {raw_key}" if "Bearer" not in raw_key else raw_key

def get_db_users():
    """Reads all users and slugs from the local SQLite DB."""
    if not os.path.exists(DB_FILE):
        print("❌ No database found. Run the backend first.")
        return []
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("SELECT user_id, thread_slug FROM user_threads")
        return c.fetchall()
    except:
        return []
    finally:
        conn.close()

def fetch_thread_history(slug, api_key):
    """Downloads chat logs for a specific slug."""
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}/thread/{slug}/chats"
    headers = {"Authorization": api_key}
    
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('history', data)
        return []
    except:
        return []

def run_audit():
    api_key = load_api_key()
    if not api_key: return

    users = get_db_users()
    print(f"\n📊 AUDIT REPORT: Found {len(users)} tracked users in database.")
    print("="*60)

    for user_id, slug in users:
        print(f"👤 USER: {user_id}")
        print(f"🆔 THREAD SLUG: {slug}")
        
        history = fetch_thread_history(slug, api_key)
        
        if not history:
            print("   (No messages in history yet)")
        else:
            print("   📜 HISTORY:")
            for msg in history[-3:]: # Show only last 3 messages to keep it clean
                role = msg.get('role', 'unknown').upper()
                text = msg.get('content', '') or msg.get('message', '')
                # Truncate long messages
                preview = (text[:75] + '..') if len(text) > 75 else text
                print(f"      [{role}]: {preview}")
        
        print("-" * 60)

if __name__ == "__main__":
    run_audit()