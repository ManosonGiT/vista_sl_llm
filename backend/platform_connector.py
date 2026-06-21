import httpx
import os
import json
import hashlib
import time
from dotenv import load_dotenv

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

async def fetch_user_progress(username: str):
    """
    Fetches student progress from the core platform using Signed HTTP Headers.
    """
    url = f"{BASE_URL}/api/v1/coach"
    headers = get_auth_headers(username)
    
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
                recent_formatted = []
                for item in recent_lessons:
                    title = item.get('lessonTitle')
                    module = item.get('moduleTitle')
                    is_completed = item.get('completed', False)
                    if title:
                        status = "Completed" if is_completed else "Accessed"
                        recent_formatted.append(f"'{title}' in '{module}' ({status})")

                text = f"STUDENT PROFILE:\n- Username: {learner.get('username')}\n"
                text += f"- Course Progress: {summary.get('completedLessons')}/{summary.get('totalLessons')} lessons ({summary.get('completionPercent')}% complete)\n"
                if recent_formatted:
                    text += f"- Recently Studied: {', '.join(recent_formatted)}\n"
                if next_lesson:
                    text += f"- NEXT RECOMMENDED LESSON: '{next_lesson.get('lessonTitle')}' in '{next_lesson.get('moduleTitle')}'\n"
                return text
            
            return "No user progress data available."
        except Exception as e:
            print(f"💥 Platform Error: {e}")
            return "Error connecting to VISTA-SL Platform."
