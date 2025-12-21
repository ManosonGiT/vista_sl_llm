import requests
import json
import sqlite3
import os
import traceback

# --- CONFIGURATION ---
BASE_URL = "https://vistachatbot.hmu.gr"
WORKSPACE_SLUG = "vista-sl_temp"
KEY_FILE = "api_keys/api_key.json"
DB_FILE = "bot_database.db"

def load_api_key():
    if not os.path.exists(KEY_FILE):
        print(f"❌ Error: {KEY_FILE} not found.")
        return None
    with open(KEY_FILE, 'r') as f:
        data = json.load(f)
        raw_key = data.get("api_key", "").strip()
        return f"Bearer {raw_key}" if "Bearer" not in raw_key else raw_key

def sync_database():
    api_key = load_api_key()
    if not api_key: return

    # 1. Initialize DB if missing
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_threads
                 (user_id TEXT PRIMARY KEY, thread_slug TEXT)''')
    
    # 2. Fetch Threads from AnythingLLM
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}"
    headers = {"Authorization": api_key}
    
    print("🔌 Fetching threads from AnythingLLM...")
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            print(f"❌ API Error {resp.status_code}: {resp.text}")
            return

        data = resp.json()
        
        # --- ROBUST EXTRACTION LOGIC ---
        
        # Step A: Handle Root List (e.g. [ {workspace...} ])
        if isinstance(data, list):
            root = data[0] if data else {}
        else:
            root = data

        # Step B: Handle "workspace" key (e.g. { "workspace": [ ... ] })
        # This is where the previous error happened.
        if 'workspace' in root:
            workspace_val = root['workspace']
            if isinstance(workspace_val, list):
                # If "workspace" is a list, take the first item
                final_workspace = workspace_val[0] if workspace_val else {}
            else:
                final_workspace = workspace_val
        else:
            # Assume the root itself is the workspace
            final_workspace = root

        # Step C: Get Threads
        if not isinstance(final_workspace, dict):
            print(f"❌ Error: Extracted workspace is not a dictionary. Got: {type(final_workspace)}")
            return

        threads = final_workspace.get('threads', [])
        
        if not threads:
            print("❌ No threads found in workspace.")
            print(f"   Debug Keys: {list(final_workspace.keys())}")
            return

        print(f"✅ Found {len(threads)} threads. Syncing to DB...")
        
        # 3. Insert into Database
        count = 0
        for t in threads:
            slug = t.get('slug')
            name = t.get('name', 'Unnamed')
            
            # Since these were created manually/via scripts, we don't have a real User ID.
            # We will generate a fake one based on the name or slug so they show up.
            if name.startswith("User-"):
                user_id = name.replace("User-", "")
            elif name == "PYTHON_SCRIPT_CHAT":
                user_id = "test_script_user"
            else:
                user_id = f"unknown_{slug[:4]}"
            
            # Save to DB
            try:
                c.execute("INSERT OR IGNORE INTO user_threads (user_id, thread_slug) VALUES (?, ?)", (user_id, slug))
                count += 1
            except Exception as e:
                print(f"   ⚠️ Could not insert {name}: {e}")

        conn.commit()
        print(f"🎉 Synced {count} users to '{DB_FILE}'.")
        print("👉 Now run 'audit_users.py' again!")

    except Exception as e:
        print(f"💥 Error: {e}")
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    sync_database()