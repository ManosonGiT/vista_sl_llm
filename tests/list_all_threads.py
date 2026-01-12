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


def list_workspace_threads(api_key):
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE_SLUG}"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    print(f"🔍 Fetching workspace details: {url}...")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"❌ API Error {response.status_code}")
            print(f"   Response: {response.text[:500]}") 
            return

        try:
            data = response.json()
        except json.JSONDecodeError:
            print("❌ Error: Server returned HTML instead of JSON.")
            return

        # --- ROBUST STRUCTURE HANDLER ---
        # 1. Handle Root
        workspace_data = None
        if isinstance(data, list):
            print(f"⚠️ Debug: Root is a LIST of {len(data)} items. Using first item.")
            workspace_data = data[0] if data else {}
        else:
            workspace_data = data

        # 2. Extract Workspace Object
        # Sometimes it's directly the object, sometimes nested under 'workspace'
        final_workspace = None
        
        if 'workspace' in workspace_data:
            possible_workspace = workspace_data['workspace']
            # Check if the value inside 'workspace' is ALSO a list (The cause of your error)
            if isinstance(possible_workspace, list):
                print(f"⚠️ Debug: 'workspace' key contains a LIST. Using first item.")
                final_workspace = possible_workspace[0] if possible_workspace else {}
            else:
                final_workspace = possible_workspace
        else:
            print("ℹ️ Debug: No 'workspace' key found. Assuming root object is the workspace.")
            final_workspace = workspace_data

        # 3. Extract Threads
        if not isinstance(final_workspace, dict):
            print(f"❌ Error: Could not extract a valid dictionary for workspace. Got: {type(final_workspace)}")
            return

        threads = final_workspace.get('threads', [])
        
        if not threads:
             print(f"⚠️ No 'threads' key found in workspace object.")
             print(f"   Keys found: {list(final_workspace.keys())}")
             return

        # 4. Success Output
        print(f"\n✅ Found {len(threads)} threads:")
        print("-" * 60)
        print(f"{'THREAD NAME':<35} | {'SLUG'}")
        print("-" * 60)
        
        for t in threads:
            name = t.get('name', 'Unnamed')
            slug = t.get('slug', 'N/A')
            print(f"{name:<35} | {slug}")
            
        print("-" * 60)
        
        found = any(t.get('name') == "PYTHON_SCRIPT_CHAT" for t in threads)
        if found:
            print("\n🎉 CONFIRMED: 'PYTHON_SCRIPT_CHAT' exists in the database!")
        else:
            print("\nℹ️ 'PYTHON_SCRIPT_CHAT' not found in this list.")

    except Exception as e:
        print(f"💥 Code Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    token = load_api_key()
    if token:
        list_workspace_threads(token)