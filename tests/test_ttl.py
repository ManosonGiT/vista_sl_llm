import sys
import os
from datetime import datetime, timedelta

# Ensure we can import local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import database

def test_ttl():
    db = database.SessionLocal()
    user_id = "test-ttl-user-999"
    
    # Clean any leftover messages
    database.clear_history(db, user_id)
    
    # 1. Save an old message (2 hours ago)
    msg1 = database.ChatMessage(
        user_id=user_id,
        role="user",
        content="I am ancient history (2 hours ago)",
        created_at=datetime.utcnow() - timedelta(hours=2)
    )
    db.add(msg1)
    db.commit()
    
    # Get recent messages. Since the only message is older than 1 hour, it should wipe the history.
    history = database.get_recent_messages(db, user_id)
    print(f"History after query 1 (expected empty list): {history}")
    assert len(history) == 0, f"Expected 0 messages, got {len(history)}"
    
    # Double check database is empty
    count = database.get_message_count(db, user_id)
    print(f"DB count (expected 0): {count}")
    assert count == 0, f"Expected 0 messages in DB, got {count}"
    
    # 2. Save a mixture: one from 45 mins ago, one from 2 hours ago, and a new one
    msg_old = database.ChatMessage(
        user_id=user_id,
        role="user",
        content="I am old (2 hours ago)",
        created_at=datetime.utcnow() - timedelta(hours=2)
    )
    msg_mid = database.ChatMessage(
        user_id=user_id,
        role="user",
        content="I am active (45 mins ago)",
        created_at=datetime.utcnow() - timedelta(minutes=45)
    )
    db.add(msg_old)
    db.add(msg_mid)
    db.commit()
    
    # Save a fresh message
    database.save_message(db, user_id, "user", "I am fresh (now)")
    
    # Get recent messages. Since there is a message from 45 mins ago (active session), it should only delete the 2-hour old message and return the active & fresh messages.
    history = database.get_recent_messages(db, user_id)
    print(f"History after query 2 (expected 2 messages: active and fresh): {history}")
    assert len(history) == 2, f"Expected 2 messages, got {len(history)}"
    assert history[0]["content"] == "I am active (45 mins ago)"
    assert history[1]["content"] == "I am fresh (now)"
    
    # Double check database contains exactly 2 messages
    count = database.get_message_count(db, user_id)
    print(f"DB count (expected 2): {count}")
    assert count == 2, f"Expected 2 messages in DB, got {count}"
    
    # Cleanup
    database.clear_history(db, user_id)
    db.close()
    print("🎉 ALL TTL TESTS PASSED!")

if __name__ == "__main__":
    test_ttl()
