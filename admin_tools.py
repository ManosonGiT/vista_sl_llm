import sys
import os
from backend import database
from sqlalchemy import func
from dotenv import load_dotenv

load_dotenv()
database.init_db()

def get_db_session():
    return database.SessionLocal()

# --- COMMAND 1: LIST USERS ---
def list_users():
    db = get_db_session()
    
    # Query all users with their message count and last active timestamp from ChatMessage
    user_stats = (
        db.query(
            database.ChatMessage.user_id,
            func.count(database.ChatMessage.id).label("msg_count"),
            func.max(database.ChatMessage.created_at).label("last_active")
        )
        .group_by(database.ChatMessage.user_id)
        .order_by(func.max(database.ChatMessage.created_at).desc())
        .all()
    )
    
    # Check if there are any legacy user threads not captured in ChatMessage
    legacy_threads = db.query(database.UserThread).all()
    db.close()

    # Build unique users set
    active_users = {stat[0] for stat in user_stats}
    legacy_only = [t for t in legacy_threads if t.user_id not in active_users]

    print(f"\n📊 FOUND {len(user_stats) + len(legacy_only)} USERS IN DATABASE")
    print(f"{'USER ID':<25} | {'MESSAGE COUNT':<15} | {'LAST ACTIVE (UTC)':<25}")
    print("-" * 75)
    
    for user_id, count, last_active in user_stats:
        last_active_str = last_active.strftime("%Y-%m-%d %H:%M:%S") if last_active else "N/A"
        print(f"{user_id:<25} | {count:<15} | {last_active_str:<25}")
        
    for thread in legacy_only:
        created_at_str = thread.created_at.strftime("%Y-%m-%d %H:%M:%S") if thread.created_at else "N/A"
        print(f"{thread.user_id:<25} | 0 (legacy)      | {created_at_str:<25} (Legacy thread: {thread.thread_slug})")
        
    print("-" * 75 + "\n")

# --- COMMAND 2: DELETE USER ---
def delete_user_history(user_id: str):
    db = get_db_session()
    
    # Check current active messages
    msg_count = database.get_message_count(db, user_id)
    
    # Check legacy user thread table
    legacy_user = db.query(database.UserThread).filter(database.UserThread.user_id == user_id).first()
    
    if msg_count == 0 and not legacy_user:
        print(f"❌ User '{user_id}' not found in active chats or legacy user threads.")
        db.close()
        return

    print(f"🔍 Found user '{user_id}':")
    if msg_count > 0:
        print(f"   💬 Has {msg_count} messages in chat_messages table.")
    if legacy_user:
        print(f"   Legacy thread slug: {legacy_user.thread_slug}")

    # Delete message history
    if msg_count > 0:
        print("   🗑️  Deleting chat history...", end=" ")
        try:
            deleted_count = database.clear_history(db, user_id)
            print(f"✅ Success (deleted {deleted_count} messages)")
        except Exception as e:
            print(f"❌ Failed: {e}")

    # Delete legacy user thread entry if exists
    if legacy_user:
        print("   🗑️  Deleting legacy user thread entry...", end=" ")
        try:
            db.delete(legacy_user)
            db.commit()
            print("✅ Success")
        except Exception as e:
            db.rollback()
            print(f"❌ Failed: {e}")
            
    db.close()

# --- COMMAND 3: WIPE ALL LOGS / CHAT HISTORY ---
def wipe_system_logs():
    confirm = input("⚠️ WARNING: This will permanently delete ALL chat messages and legacy user threads from the database. Are you sure? (y/N): ")
    if confirm.lower() != 'y':
        print("❌ Operation cancelled.")
        return

    db = get_db_session()
    print("\n☢️  ATTEMPTING DATABASE WIPE...")
    try:
        msg_count = db.query(database.ChatMessage).delete()
        thread_count = db.query(database.UserThread).delete()
        db.commit()
        print(f"✅ SUCCESS! Deleted {msg_count} active chat messages and {thread_count} legacy user threads.")
    except Exception as e:
        db.rollback()
        print(f"💥 Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python admin_tools.py [list | delete <id> | wipe_logs]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        list_users()
    elif command == "delete":
        if len(sys.argv) < 3:
            print("Error: Please provide a user_id to delete.")
            print("Usage: python admin_tools.py delete <user_id>")
            sys.exit(1)
        delete_user_history(sys.argv[2])
    elif command == "wipe_logs":
        wipe_system_logs()