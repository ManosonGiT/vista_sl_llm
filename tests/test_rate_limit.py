import httpx
import asyncio
import sys
import os

# Ensure we can import local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

BASE_URL = "http://localhost:8000"
USER_ID = "rate-limit-test-user"
TOKEN = "dummy-token"

async def test_rate_limiting():
    print("=== TESTING RATE LIMITING ===")
    
    payload = {
        "userId": USER_ID,
        "token": TOKEN,
        "message": "Hello there!"
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Send 15 requests rapidly. Since default limit is 10, requests 11-15 should throw 429
        success_count = 0
        limited_count = 0
        
        for i in range(1, 16):
            try:
                resp = await client.post(f"{BASE_URL}/chat", json=payload)
                if resp.status_code == 200:
                    success_count += 1
                    print(f"Request {i}: Success (200)")
                elif resp.status_code == 429:
                    limited_count += 1
                    print(f"Request {i}: Rate Limited (429) - {resp.json().get('detail')}")
                else:
                    print(f"Request {i}: Unexpected status code {resp.status_code}")
            except Exception as e:
                print(f"Request {i} failed: {e}")
                
        print(f"\nSummary:")
        print(f"  Successes: {success_count}")
        print(f"  Rate Limits (429): {limited_count}")
        
        assert limited_count > 0, "Error: Rate limiting was NOT triggered!"
        print("\n✅ RATE LIMITING TEST PASSED!")

if __name__ == "__main__":
    asyncio.run(test_rate_limiting())
