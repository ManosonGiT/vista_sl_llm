import sys
import requests

BASE_URL = "http://localhost:8000"

def test_full_stack():
    print("=== VISTA-SL BACKEND DIAGNOSTIC TOOL ===")
    print("Connecting to backend server...")
    
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=10)
    except requests.exceptions.ConnectionError:
        print("\n❌ Connection FAILED: Backend server is not running on http://localhost:8000")
        print("👉 Did you start Docker Compose ('docker compose up -d')?")
        sys.exit(1)
        
    if resp.status_code == 200:
        data = resp.json()
        print("\n1️⃣  Checking Backend Service Status...")
        print(f"   ✅ Server Status: ONLINE")
        print(f"   🤖 Configured Model: {data.get('model')}")
        
        print("\n2️⃣  Checking Database Connection (From Backend)...")
        if data.get("database") == "healthy":
            print("   ✅ Connection Successful. Database is Healthy.")
        else:
            print("   ❌ Database Connection FAILED! (Check backend logs for errors)")
            
        print("\n3️⃣  Checking LLM Provider Connection...")
        if data.get("groq_api") == "healthy":
            print("   ✅ Connection Successful. Groq API is Healthy.")
        else:
            print("   ❌ LLM Provider Connection FAILED! (Check your API keys in .env)")
            
        print("\n4️⃣  Checking Platform Progress Fetch...")
        import json
        import os
        import asyncio
        import httpx
        
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        try:
            from backend.platform_connector import fetch_user_progress
            
            cred_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend_simulate_key.json"))
            if os.path.exists(cred_path):
                with open(cred_path, "r") as f:
                    cred_data = json.load(f)
                    user_data = cred_data.get("user_1", {})
                    username = user_data.get("username")
                    token = user_data.get("token")
                
                # A. Test Session Token/Cookie (Current Platform Auth)
                if token:
                    print(f"   [A] Testing fetch using user session cookie/token...")
                    async def fetch_with_cookie():
                        cookie_headers = {
                            "Cookie": token,
                            "Accept": "application/json"
                        }
                        async with httpx.AsyncClient(verify=False) as client:
                            resp = await client.get("https://vistasl.eelvex.net/api/v1/coach", headers=cookie_headers, timeout=10.0)
                            return resp
                    
                    loop = asyncio.get_event_loop()
                    resp = loop.run_until_complete(fetch_with_cookie())
                    if resp.status_code == 200:
                        print("       ✅ Token Session Fetch Successful!")
                        try:
                            resp_data = resp.json()
                            print("       📊 Full Platform History & Profile Data:")
                            # Indent each line by 10 spaces to keep formatting clean
                            formatted_json = json.dumps(resp_data, indent=4, ensure_ascii=False)
                            for line in formatted_json.split("\n"):
                                print(f"          {line}")
                        except Exception as parse_err:
                            print(f"       ❌ Failed to parse response JSON: {parse_err}")
                            print(f"          Response snippet: {resp.text[:100]}...")
                    else:
                        print(f"       ❌ Token Session Fetch FAILED (Status {resp.status_code})")
                
                # B. Test HMAC Hash Signature (Future Middleware Auth)
                if username:
                    print(f"   [B] Testing fetch using HMAC signature hashing (username: {username})...")
                    loop = asyncio.get_event_loop()
                    progress_data = loop.run_until_complete(fetch_user_progress(username))
                    
                    if "Error connecting" in progress_data or "No user progress" in progress_data:
                        print(f"       ❌ HMAC Signature Fetch FAILED: (Expected as hashing isn't deployed on platform yet)")
                    else:
                        print("       ✅ HMAC Signature Fetch Successful:")
                        for line in progress_data.split("\n"):
                            if line.strip():
                                print(f"          {line}")
                else:
                    print("   ⚠️  Skip: No username found in frontend_simulate_key.json")
            else:
                print("   ⚠️  Skip: frontend_simulate_key.json not found")
        except Exception as plat_err:
            print(f"   ❌ Platform progress fetch error: {plat_err}")
            
        print("\n" + "=" * 50)
        if data.get("status") == "healthy":
            print("🎉 SYSTEM IS READY FOR PRODUCTION.")
        else:
            print("⚠️  SYSTEM IS DEGRADED.")
    else:
        print(f"\n❌ Unexpected response from server: HTTP {resp.status_code}")
        print(resp.text)
        sys.exit(1)

if __name__ == "__main__":
    test_full_stack()
