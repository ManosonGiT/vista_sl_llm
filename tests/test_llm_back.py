import requests
import json
import os

# --- CONFIGURATION ---
BASE_URL = "https://vistachatbot.hmu.gr"
WORKSPACE_SLUG = "vista-sl_temp"
KEY_FILE = os.abspath(os.path.join(os.path.dirname(__file__), "..", "api_keys", "api_key.json"))

def load_api_key():
    if not os.path.exists(KEY_FILE):
        print(f"❌ Error: {KEY_FILE} not found.")
        return None

    with open(KEY_FILE, 'r') as f:
        data = json.load(f)
        raw_key = data.get("api_key", "").strip()
        return f"Bearer {raw_key}" if "Bearer" not in raw_key else raw_key

def test_full_flow(api_key):
    print("\n--- TEST: CREATE THREAD & CHAT IN IT ---")
    
    # 1. CREATE THE THREAD
    create_url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}/thread/new"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    
    # We use a unique name so you can find it easily
    thread_name = "PYTHON_SCRIPT_CHAT"
    payload = {"name": thread_name}

    slug = None

    try:
        print(f"1️⃣ Creating Thread '{thread_name}'...")
        resp = requests.post(create_url, headers=headers, json=payload, timeout=20)
        
        if resp.status_code == 200:
            data = resp.json()
            thread_info = data.get('thread', data)
            slug = thread_info.get('slug')
            print(f"   ✅ Thread Created! Slug: {slug}")
        else:
            print(f"   ❌ Creation Failed: {resp.text}")
            return

    except Exception as e:
        print(f"   💥 Error: {e}")
        return

    # 2. CHAT INSIDE THAT THREAD
    # Notice the URL now includes the thread slug!
    chat_url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}/thread/{slug}/chat"
    
    chat_payload = {
        "message": "Hello! I am writing this message inside the thread so you can see me in the GUI.",
        "mode": "chat"
    }

    try:
        print(f"2️⃣ Sending Message to Thread '{thread_name}'...")
        resp = requests.post(chat_url, headers=headers, json=chat_payload, timeout=20)
        
        if resp.status_code == 200:
            print("   ✅ SUCCESS! Message sent.")
            print("   👉 ACTION: Go to your browser, REFRESH the page, and click 'PYTHON_SCRIPT_CHAT' in the sidebar.")
        else:
            print(f"   ❌ Chat Failed: {resp.text}")

    except Exception as e:
        print(f"   💥 Error: {e}")

if __name__ == "__main__":
    token = load_api_key()
    if token:
        test_full_flow(token)
