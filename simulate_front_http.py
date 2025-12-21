import requests
import json
import os
import sys

# Config
SERVER_URL = "http://localhost:5000/chat"
SIMULATION_FILE = "frontend_simulate_key.json"

def run_http_simulation(user_key="user_1"):
    # 1. Load User Credentials
    if not os.path.exists(SIMULATION_FILE):
        print(f"❌ {SIMULATION_FILE} missing.")
        return

    with open(SIMULATION_FILE, 'r') as f:
        users = json.load(f)
        current_user = users.get(user_key)
    
    if not current_user:
        print(f"❌ User key '{user_key}' not found.")
        return

    print(f"\n🔑 LOGGED IN AS: {current_user['username']}")
    
    # 2. Get User Input
    try:
        user_msg = input("💬 Enter your message: ")
    except KeyboardInterrupt:
        return

    # 3. Prepare Payload
    payload = {
        "userId": current_user['userId'],
        "token": current_user['token'], # We send the raw cookie/token
        "message": user_msg
    }

    print("\n📡 Sending request to Backend...", end="", flush=True)

    # 4. Send POST Request & Handle Streaming Response
    try:
        response = requests.post(SERVER_URL, json=payload, stream=True)
        
        if response.status_code == 200:
            print("\r🤖 Assistant: ", end="", flush=True)
            
            # Read SSE Stream
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data:"):
                        data_str = decoded[5:].strip()
                        if data_str == "[DONE]": break
                        
                        try:
                            # Parse the JSON wrapped by the server
                            json_data = json.loads(data_str)
                            token = json_data.get('token', '')
                            sys.stdout.write(token)
                            sys.stdout.flush()
                        except:
                            pass
            print("\n" + "-"*50)
            print("✅ Complete.")
        else:
            print(f"\n❌ Server Error {response.status_code}: {response.text}")

    except Exception as e:
        print(f"\n💥 Connection Error: Is server.py running? ({e})")

if __name__ == "__main__":
    selected_user = sys.argv[1] if len(sys.argv) > 1 else "user_1"
    run_http_simulation(selected_user)