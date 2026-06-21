from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text
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

import sys

if not engine:
    print("Critical Error: Could not connect to PostgreSQL database.")
    print("Ensure PostgreSQL is running and you ran './setup_postgres.sh' first!")
    sys.exit(1)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELS ---

class UserThread(Base):
    """Tracks user sessions (kept for backward compatibility)."""
    __tablename__ = "user_threads"

    user_id = Column(String, primary_key=True, index=True)
    thread_slug = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    """Stores every user and assistant message for conversation history."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)  # "user", "assistant", or "system"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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

# --- CRUD: Thread Management (legacy) ---
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

# --- CRUD: Chat History ---
def save_message(db, user_id: str, role: str, content: str):
    """Save a single message (user or assistant) to the database."""
    msg = ChatMessage(user_id=user_id, role=role, content=content)
    db.add(msg)
    db.commit()
    return msg

def get_recent_messages(db, user_id: str, limit: int = 20):
    """
    Fetch the last N messages for a user, returned in chronological order.
    Returns a list of dicts: [{"role": "user", "content": "..."}, ...]
    """
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    # Reverse so oldest is first (chronological order for the LLM)
    messages.reverse()
    return [{"role": m.role, "content": m.content} for m in messages]

def clear_history(db, user_id: str):
    """Wipe all chat history for a specific user."""
    count = db.query(ChatMessage).filter(ChatMessage.user_id == user_id).delete()
    db.commit()
    return count

def get_message_count(db, user_id: str) -> int:
    """Return total message count for a user."""
    return db.query(ChatMessage).filter(ChatMessage.user_id == user_id).count()
