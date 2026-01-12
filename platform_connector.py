import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("PLATFORM_URL", "https://vistasl.eelvex.net")

def get_headers(token_string: str):
    # 🔑 SMART TOKEN HANDLER
    if "remember_token" in token_string or "session=" in token_string:
        return {
            "Cookie": token_string, 
            "User-Agent": "VISTA-SL-Middleware/1.0", 
            "Accept": "application/json"
        }
    return {
        "Authorization": token_string if "Bearer" in token_string else f"Bearer {token_string}", 
        "Accept": "application/json"
    }

async def fetch_user_progress(token_string: str):
    url = f"{BASE_URL}/api/v1/coach"
    headers = get_headers(token_string)
    
    async with httpx.AsyncClient(verify=False) as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            
            if resp.status_code == 200:
                data = resp.json()
                learner = data.get('learner', {})
                summary = data.get('progressSummary', {})
                recs = data.get('recommendations', {})
                next_lesson = recs.get('nextLesson')
                
                text = f"STUDENT PROFILE:\n- Username: {learner.get('username')}\n"
                text += f"- Progress: {summary.get('completedLessons')}/{summary.get('totalLessons')} ({summary.get('completionPercent')}% /{summary.get('recentLessons')}) completed.\n"
                if next_lesson:
                    text += f"- NEXT RECOMMENDATION: '{next_lesson.get('lessonTitle')}' (Unit: {next_lesson.get('moduleTitle')})\n"
                return text
            
            return "No user progress data available."
        except Exception as e:
            print(f"💥 Platform Error: {e}")
            return "Error connecting to VISTA-SL Platform."