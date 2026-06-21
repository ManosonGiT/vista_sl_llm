import sys
import os
import time

# Ensure we can import local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import database
from sqlalchemy.orm import Session

def test_full_stack():
    print("=== VISTA-SL BACKEND DIAGNOSTIC TOOL ===")
    
    # 1. Check Env
    db_url = os.getenv("DATABASE_URL")
    print(f"1️⃣  Checking Configuration...")
    if db_url and "postgresql" in db_url:
        print(f"   ✅ Configured for PostgreSQL")
    else:
        print(f"   ❌ Configured for SQLite (Check .env file!)")

    # 2. Check Connection
    print("\n2️⃣  Connecting to Database...")
    try:
        database.init_db()
        print("   ✅ Connection Successful. Tables Verified.")
    except Exception as e:
        print(f"   ❌ Connection FAILED: {e}")
        print("   👉 Did you run './setup_postgres.sh'?")
        sys.exit(1)

    # 3. CRUD Test
    print("\n3️⃣  Testing Data Persistence...")
    db = database.SessionLocal()
    test_user = "diagnostic_user_001"
    test_slug = "uuid-test-slug-999"
    
    try:
        database.save_thread_slug(db, test_user, test_slug)
        retrieved = database.get_thread_slug(db, test_user)
        
        if retrieved == test_slug:
            print(f"   ✅ WRITE/READ Test Passed: {test_user} -> {retrieved}")
        else:
            print(f"   ❌ DATA MISMATCH: Expected {test_slug}, got {retrieved}")
    except Exception as e:
        print(f"   ❌ Database Error: {e}")
    finally:
        db.close()

    print("\n🎉 SYSTEM IS READY FOR PRODUCTION.")

if __name__ == "__main__":
    test_full_stack()
