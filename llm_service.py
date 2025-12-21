import requests
import json
import os

# --- CONFIGURATION ---
BASE_URL = "https://vistachatbot.hmu.gr"
WORKSPACE_SLUG = "vista-sl_temp"
KEY_FILE = "api_keys/api_key.json"

def load_api_key():
    """Loads and formats the Admin API Key."""
    if not os.path.exists(KEY_FILE):
        print(f"❌ Error: {KEY_FILE} not found.")
        return None
    with open(KEY_FILE, 'r') as f:
        data = json.load(f)
        raw_key = data.get("api_key", "").strip()
        return f"Bearer {raw_key}" if "Bearer" not in raw_key else raw_key

def get_headers():
    key = load_api_key()
    return {
        "Authorization": key, 
        "Content-Type": "application/json",
        "Accept": "text/event-stream" 
    } if key else None

# --- CORE FUNCTIONS ---

def create_thread(user_id):
    """Creates a thread named 'User-{user_id}' and returns the slug."""
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}/thread/new"
    headers = get_headers()
    if not headers: return None

    payload = {"name": f"User-{user_id}"}
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            thread_info = data.get('thread', data)
            return thread_info.get('slug')
        else:
            print(f"❌ Create Thread Failed: {resp.text}")
    except Exception as e:
        print(f"💥 Create Thread Error: {e}")
    return None

def fetch_chat_history(thread_slug):
    """Fetches full conversation history."""
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}/thread/{thread_slug}/chats"
    headers = get_headers()
    if not headers: return []

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            history = data.get('history', data)
            return history if isinstance(history, list) else []
    except Exception as e:
        print(f"💥 Fetch History Error: {e}")
    return []

def stream_chat(thread_slug, message):
    """
    Sends message and yields tokens one by one.
    Uses the /stream-chat endpoint for real-time tokens.
    """
    # ⚡️ CRITICAL CHANGE: Use 'stream-chat' instead of 'chat'
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}/thread/{thread_slug}/stream-chat"
    headers = get_headers()
    if not headers: return

    payload = {
        "message": message,
        "mode": "chat"
    }

    try:
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=30) as r:
            if r.status_code != 200:
                yield f"Error {r.status_code}: {r.text}"
                return

            # Check if server actually ignored streaming request (fallback)
            content_type = r.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                # Server sent a blocking JSON response
                try:
                    full_json = r.json()
                    yield full_json.get('textResponse', '')
                except:
                    yield r.text
                return

            # Process SSE Stream
            for line in r.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data:"):
                        try:
                            json_str = decoded[5:].strip()
                            if json_str == "[DONE]": break
                            
                            chunk_data = json.loads(json_str)
                            token = chunk_data.get('token') or chunk_data.get('textResponse')
                            if token:
                                yield token
                        except:
                            pass
    except Exception as e:
        yield f"Stream Error: {e}"