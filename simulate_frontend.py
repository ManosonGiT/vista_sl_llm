import requests
import json
import os
import sys

# CONFIGURATION
SERVER_URL = "http://localhost:8000/chat"
CREDENTIALS_FILE = "frontend_simulate_key.json"

def run_simulation(user_key="user_1"):
    # 1. Load Credentials
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Error: {CREDENTIALS_FILE} not found.")
        return

    with open(CREDENTIALS_FILE, 'r') as f:
        data = json.load(f)
        user_data = data.get(user_key)
    
    if not user_data:
        print(f"❌ Error: User '{user_key}' not found in JSON.")
        return

    print(f"\n🔑 LOGGED IN AS: {user_data['username']} ({user_data['userId']})")
    print(f"📡 CONNECTING TO: {SERVER_URL}")

    # 2. Get User Input
    try:
        user_input = input("\n💬 Enter your message: ")
    except KeyboardInterrupt:
        print("\n👋 Exiting.")
        return

    # 3. Construct Payload (The exact JSON the backend expects)
    payload = {
        "userId": user_data['userId'],
        "token": user_data['token'],
        "message": user_input
    }

    print("\n🤖 Assistant is typing...", end="", flush=True)

    # 4. Send Request & Stream Response
    try:
        # stream=True is critical for SSE
        with requests.post(SERVER_URL, json=payload, stream=True, timeout=30) as response:
            
            # Clear the "typing..." line
            print("\r" + " "*30 + "\r🤖 Assistant: ", end="", flush=True)
            
            if response.status_code != 200:
                print(f"❌ Server Error {response.status_code}: {response.text}")
                return

            # 5. Parse Server-Sent Events (SSE)
            # Format is: data: {"token": "hello"}\n\n
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    
                    if decoded_line.startswith("data:"):
                        json_str = decoded_line[5:].strip() # Remove "data: "
                        
                        if json_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(json_str)
                            token = data.get("token", "")
                            # Print token immediately without newline
                            sys.stdout.write(token)
                            sys.stdout.flush()
                        except json.JSONDecodeError:
                            pass
                            
    except requests.exceptions.ConnectionError:
        print("\n❌ Connection Failed. Is the server running?")
        print("👉 Run: uvicorn main:app --port 8000")
    except Exception as e:
        print(f"\n❌ Error: {e}")

    print("\n" + "-"*50)
    print("✅ Interaction Complete.")

if __name__ == "__main__":
    # Allow switching users via command line: python simulate_frontend.py user_2
    selected_user = sys.argv[1] if len(sys.argv) > 1 else "user_1"
    run_simulation(selected_user)