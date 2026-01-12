import requests
import json
import os
import traceback
from dotenv import load_dotenv

load_dotenv()
# --- CONFIGURATION ---
BASE_URL = "https://vistachatbot.hmu.gr"
WORKSPACE_SLUG = "vista-sl_temp"
KEY_FILE = os.getenv("ANYTHING_LLM_KEY")

def load_api_key():
    
    if not KEY_FILE:
        print("❌ Error: ANYTHING_LLM_KEY not found in environment.")
        return None
    
    raw_key = KEY_FILE.strip()
    return raw_key if raw_key.startswith("Bearer ") else f"Bearer {raw_key}"

def get_history(api_key):
    # 1. First, get the list of threads to find a valid slug
    list_url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    
    try:
        # Fetch Workspace Data
        print(f"Fetching thread list...")
        resp = requests.get(list_url, headers=headers)
        
        if resp.status_code != 200:
            print(f"API Error {resp.status_code}: {resp.text}")
            return

        data = resp.json()
        
        # 1. Handle Root (Is it a list?)
        workspace_data = None
        if isinstance(data, list):
            workspace_data = data[0] if data else {}
        else:
            workspace_data = data

        # 2. Extract Workspace Object (Is it nested?)
        final_workspace = None
        
        # Check if 'workspace' key exists and handles if THAT is a list
        if isinstance(workspace_data, dict) and 'workspace' in workspace_data:
            possible_workspace = workspace_data['workspace']
            if isinstance(possible_workspace, list):
                final_workspace = possible_workspace[0] if possible_workspace else {}
            else:
                final_workspace = possible_workspace
        else:
            final_workspace = workspace_data

        # 3. Final Safety Check before accessing .get()
        if not isinstance(final_workspace, dict):
            print(f"Error: Parsed workspace data is not a dictionary. It is: {type(final_workspace)}")
            print(f"Content: {final_workspace}")
            return

        threads = final_workspace.get('threads', [])
        
        if not threads:
            print("No threads found.")
            return

        # 2. Pick the most recent thread
        target_thread = threads[-1] # Pick the last created one
        slug = target_thread.get('slug')
        name = target_thread.get('name', 'Unnamed')
        
        print(f"Fetching history for thread: {name} (Slug: {slug})")
        print("-" * 50)

        # 3. Fetch History for this specific thread
        history_url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}/thread/{slug}/chats"
        hist_resp = requests.get(history_url, headers=headers)
        
        if hist_resp.status_code == 200:
            history_data = hist_resp.json()
            # The history is usually a list of message objects
            messages = history_data.get('history', history_data)
            
            if not messages:
                print("📭 This thread is empty (no messages).")
            else:
                for msg in messages:
                    role = msg.get('role', 'unknown').upper() # user or assistant
                    content = msg.get('content', '') or msg.get('message', '')
                    print(f"[{role}]: {content}")
                    print("-" * 20)
        else:
            print(f"❌ Failed to get history: {hist_resp.status_code}")
            print(hist_resp.text)

    except Exception as e:
        print(f"💥 Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    token = load_api_key()
    if token:
        get_history(token)