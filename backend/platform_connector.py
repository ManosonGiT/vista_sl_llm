import httpx
import os
import json
import hashlib
import time
from dotenv import load_dotenv
from backend.logging_config import logger

load_dotenv()

BASE_URL = os.getenv("PLATFORM_URL", "https://vistasl.eelvex.net")
COACH_SECRET_KEY = os.getenv("COACH_SECRET_KEY", "")

def get_auth_headers(username: str) -> dict:
    """
    Generates authentication headers by hashing the username and current unix timestamp
    using SHA-256 and the COACH_SECRET_KEY.
    """
    timestamp = str(int(time.time()))
    # Concatenate: username + timestamp + secret_key
    raw_string = f"{username}{timestamp}{COACH_SECRET_KEY}"
    signature = hashlib.sha256(raw_string.encode("utf-8")).hexdigest()
    
    return {
        "X-User": username,
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Accept": "application/json",
        "User-Agent": "VISTA-SL-Middleware/1.0"
    }

async def fetch_user_progress(username: str, token: str = None):
    """
    Fetches student progress from the core platform using Signed HTTP Headers.
    Falls back to using user session token/cookie if provided.
    """
    url = f"{BASE_URL}/api/v1/coach"
    headers = get_auth_headers(username)
    if token:
        if "remember_token" in token or "session" in token:
            headers["Cookie"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
    
    async with httpx.AsyncClient(verify=False) as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            
            if resp.status_code == 200:
                data = resp.json()
                learner = data.get('learner', {})
                summary = data.get('progressSummary', {})
                recs = data.get('recommendations', {})
                next_lesson = recs.get('nextLesson')
                
                recent_lessons = summary.get('recentLessons', [])
                completed_titles = []
                for item in recent_lessons:
                    title = item.get('lessonTitle')
                    is_completed = item.get('completed', False)
                    if title and is_completed:
                        completed_titles.append(f"'{title}'")
                
                text = f"STUDENT PROFILE:\n"
                text += f"- Completed: {summary.get('completedLessons')}/{summary.get('totalLessons')} lessons\n"
                if completed_titles:
                    text += f"- Recently completed: {', '.join(completed_titles)}\n"
                if next_lesson:
                    text += f"- Recommended next: '{next_lesson.get('lessonTitle')}' in '{next_lesson.get('moduleTitle')}'\n"
                return text
            
            logger.warning(f"Platform returned status {resp.status_code}: {resp.text}")
            return "No user progress data available."
        except Exception as e:
            logger.error(f"Platform Error: {e}")
            return "Error connecting to VISTA-SL Platform."
