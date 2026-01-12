from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os
from dotenv import load_dotenv
import time

load_dotenv()

# Load DB URL
DATABASE_URL = os.getenv("DATABASE_URL")

# --- RETRY LOGIC FOR STARTUP ---
# Sometimes the DB takes a second to wake up if started via script
engine = None
for i in range(5):
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            pass # Just testing connection
        break
    except Exception as e:
        print(f"⏳ Waiting for Database... ({i+1}/5)")
        time.sleep(2)

if not engine:
    print("Critical Error: Could not connect to PostgreSQL.")
    print(" Ensure you ran './setup_postgres.sh' first!")
    # Fallback to prevent immediate crash, though functionality will break
    DATABASE_URL = "sqlite:///./local_backup.db"
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- THE MODEL ---
class UserThread(Base):
    __tablename__ = "user_threads"

    user_id = Column(String, primary_key=True, index=True)
    thread_slug = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# --- AUTO-SETUP ---
def init_db():
    """Checks tables. Creates them if missing."""
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- CRUD ---
def get_thread_slug(db, user_id: str):
    user = db.query(UserThread).filter(UserThread.user_id == user_id).first()
    return user.thread_slug if user else None

def save_thread_slug(db, user_id: str, slug: str):
    user = db.query(UserThread).filter(UserThread.user_id == user_id).first()
    if user:
        user.thread_slug = slug
        user.last_active = datetime.utcnow()
    else:
        new_user = UserThread(user_id=user_id, thread_slug=slug)
        db.add(new_user)
    db.commit()