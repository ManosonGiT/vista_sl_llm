import requests
import json
import os

# --- CONFIGURATION ---
BASE_URL = "https://vistachatbot.hmu.gr"
# Based on your screenshot, the working workspace is 'vista-sl_temp'
WORKSPACE_SLUG = "vista-sl_temp" 
TOKEN_FILE = "token.json"

def load_token():
    if not os.path.exists(TOKEN_FILE):
        print(f"❌ Error: Could not find {TOKEN_FILE}")
        return None
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("token", "").strip()
    except Exception as e:
        print(f"❌ Error reading JSON: {e}")
        return None

def chat_with_backend(user_message):
    token = load_token()
    if not token: return

    # 1. USE THE BROWSER ENDPOINT (stream-chat)
    endpoint = f"{BASE_URL}/api/workspace/{WORKSPACE_SLUG}/stream-chat"

    # 2. ADD THE "DISGUISE" HEADERS (Origin & Referer)
    # The server rejects requests without these!
    headers = {
        "Authorization": f"Bearer {token}" if not token.startswith("Bearer") else token,
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/workspace/{WORKSPACE_SLUG}"
    }

    payload = {
        "message": user_message,
        "mode": "chat"
    }

    print(f"🔌 Connecting to: {endpoint}")

    try:
        # 3. ENABLE STREAMING (stream=True)
        response = requests.post(endpoint, headers=headers, json=payload, stream=True)

        if response.status_code == 200:
            print("\n✅ SUCCESS! Stream started...")
            
            # 4. READ THE STREAM BIT BY BIT
            full_reply = ""
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    # The stream sends data like: "data: {...}"
                    if decoded_line.startswith("data:"):
                        try:
                            json_content = json.loads(decoded_line[5:]) # Skip "data:"
                            
                            # Different models send different chunks. 
                            # We look for specific keys usually found in AnythingLLM streams.
                            chunk = json_content.get('token') or json_content.get('textResponse') or ""
                            
                            # Print it live to the console
                            print(chunk, end="", flush=True)
                            full_reply += chunk
                            
                            # If we get the sources, show them at the end
                            if json_content.get('sources'):
                                print(f"\n\n📚 Sources found: {len(json_content['sources'])}")

                        except:
                            pass
            print("\n\n(Stream Finished)")
        else:
            print(f"\n❌ Failed ({response.status_code})")
            print(f"Server said: {response.text[:200]}") # Print first 200 chars of error

    except Exception as e:
        print(f"\n❌ Connection Error: {e}")

if __name__ == "__main__":
    chat_with_backend("Hello, do you know how to sign 'Family'?")