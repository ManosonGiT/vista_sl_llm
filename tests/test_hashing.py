import sys
import os
import hashlib
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.platform_connector import get_auth_headers

def test_headers_signature():
    print("=== TESTING MIDDLEWARE AUTH HEADER SIGNING ===")
    
    # Setup test variables
    username = "test-history-user-001"
    secret = "temp_coach_secret_for_dev"
    os.environ["COACH_SECRET_KEY"] = secret
    
    # Import again to refresh os.environ if needed, but since it reads from env:
    # get_auth_headers uses os.getenv("COACH_SECRET_KEY", "") which reads dynamic env variables.
    
    headers = get_auth_headers(username)
    print("Generated Headers:")
    for k, v in headers.items():
        print(f"  {k}: {v}")
        
    assert headers["X-User"] == username
    assert "X-Timestamp" in headers
    assert "X-Signature" in headers
    
    # Recalculate signature locally to assert validity
    timestamp = headers["X-Timestamp"]
    raw_str = f"{username}{timestamp}{secret}"
    expected_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    
    assert headers["X-Signature"] == expected_hash
    print("\n✅ SIGNATURE TEST PASSED!")

if __name__ == "__main__":
    test_headers_signature()
