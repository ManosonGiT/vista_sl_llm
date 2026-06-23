"""
End-to-End Test: History, RAG, and Groq Streaming

Sends 3 messages to verify:
1. Fresh context fetch + RAG injection
2. Cached context reuse
3. Conversation memory (AI should recall earlier messages)
"""

import httpx
import asyncio
import json
import socket

import os

BASE_URL = "http://localhost:8000"
USER_ID = "test-history-user-001"
TOKEN = "dummy-token"

# Try to load user and token from frontend_simulate_key.json
cred_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend_simulate_key.json"))
if os.path.exists(cred_path):
    try:
        with open(cred_path, "r") as f:
            cred_data = json.load(f)
            user_data = cred_data.get("user_1", {})
            USER_ID = user_data.get("username", USER_ID)
            TOKEN = user_data.get("token", TOKEN)
            print(f"Loaded credentials for user: {USER_ID}")
    except Exception as e:
        print(f"⚠️ Error loading frontend_simulate_key.json: {e}")


def is_server_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', 8000)) == 0


async def send_chat(message: str):
    print(f"\n[USER] {message}")
    print("[AI] ", end="", flush=True)

    payload = {
        "userId": USER_ID,
        "token": TOKEN,
        "message": message
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream("POST", f"{BASE_URL}/chat", json=payload) as response:
                if response.status_code != 200:
                    print(f"Server Error {response.status_code}")
                    return

                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            token = data.get("token", "")
                            print(token, end="", flush=True)
                        except:
                            pass
            print()
        except Exception as e:
            print(f"\n[ERROR] {e}")


async def check_health():
    """Check system health before running tests."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/health")
            if resp.status_code == 200:
                health = resp.json()
                print(f"   Groq API: {health.get('groq_api')}")
                print(f"   Database: {health.get('database')}")
                print(f"   Model:    {health.get('model')}")
                print(f"   Status:   {health.get('status')}")
                return health.get("status") == "healthy"
        except:
            pass
    return False


async def run_test():
    if not is_server_running():
        print("❌ Server is NOT running at http://localhost:8000")
        print("👉 Please run 'python3 -m backend.main' in another terminal first.")
        return

    print("🚀 Running VISTA-SL End-to-End Test")
    print("=" * 50)

    # 0. Health Check
    print("\n🏥 Health Check:")
    healthy = await check_health()
    if not healthy:
        print("⚠️  System is degraded. Continuing anyway...\n")

    # Reset history to ensure clean test runs
    print("\n🧹 Resetting user chat history & cache...")
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.post(f"{BASE_URL}/chat/clear", json={"userId": USER_ID})
            if resp.status_code == 200:
                print("   ✅ History cleared successfully.")
            else:
                print(f"   ⚠️ Could not clear history (Status {resp.status_code})")
        except Exception as e:
            print(f"   ⚠️ Could not connect to clear history: {e}")

    # 1. First Message (Fresh context fetch + RAG search)
    print("\n--- Test 1: Fresh Context + RAG ---")
    await send_chat("What letter comes after Α in the Greek alphabet?")

    await asyncio.sleep(1)

    # 2. Second Message (Cached context + different RAG query)
    print("\n--- Test 2: Cached Context ---")
    await send_chat("Can you teach me the word for 'cat' in Greek Sign Language?")

    await asyncio.sleep(1)

    # 3. Third Message (Memory check)
    print("\n--- Test 3: Memory Recall ---")
    await send_chat("What was the first thing I asked you?")

    await asyncio.sleep(1)

    # 4. Fourth Message (Querying recommended lesson based on fetched progress with token)
    print("\n--- Test 4: Real User Progress Recommendation with Session Token ---")
    await send_chat("What lesson should I watch next?")

    print("\n" + "=" * 50)
    print("✅ Test sequence complete.")
    print("📋 Check server logs for: ⚡ Cached Context, 📚 RAG hits, 💾 Saved responses")


if __name__ == "__main__":
    asyncio.run(run_test())
