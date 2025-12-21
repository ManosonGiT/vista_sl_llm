import requests
import urllib3
import json

# Disable SSL warnings for the platform connection
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://vistasl.eelvex.net"

def get_headers(token_string):
    if "remember_token" in token_string or "session=" in token_string:
        return {
            "Cookie": token_string,
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
    else:
        return {
            "Authorization": token_string if "Bearer" in token_string else f"Bearer {token_string}",
            "Accept": "application/json"
        }

def fetch_all_lessons(token_string):
    """Scrapes all lessons to provide curriculum context."""
    # Try the singular endpoint first
    url = f"{BASE_URL}/api/v1/game/sign"
    headers = get_headers(token_string)
    
    print(f"🔌 [Platform] Fetching lessons...")
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        
        # Fallback to plural if singular fails
        if resp.status_code == 404:
            url = f"{BASE_URL}/api/v1/game/signs"
            resp = requests.get(url, headers=headers, verify=False, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', data) if isinstance(data, dict) else data
            if not isinstance(items, list): items = []
            
            print(f"   ✅ Found {len(items)} lessons.")
            
            # Format: "- ID 123: Title (Module: ModuleName)"
            simplified_lessons = []
            for item in items:
                l_id = item.get('lessonId') or item.get('id')
                title = item.get('title')
                module = item.get('moduleTitle') or "General"
                simplified_lessons.append(f"- ID {l_id}: {title} (Module: {module})")
            
            return simplified_lessons
        else:
            print(f"   ❌ Failed to fetch lessons: {resp.status_code}")
            return []
    except Exception as e:
        print(f"   💥 Connection Error: {e}")
        return []

def fetch_user_progress(token_string):
    """
    Fetches and PARSES the Coach API JSON to generate a readable summary.
    """
    url = f"{BASE_URL}/api/v1/coach"
    headers = get_headers(token_string)
    
    print(f"🔌 [Platform] Fetching user progress...")
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            print("   ✅ User progress retrieved.")
            
            # --- PARSING LOGIC ---
            learner = data.get('learner', {})
            summary = data.get('progressSummary', {})
            recs = data.get('recommendations', {})
            next_lesson = recs.get('nextLesson')
            
            # Build a clean text summary for the LLM context
            progress_text = f"STUDENT PROFILE:\n"
            progress_text += f"- Username: {learner.get('username', 'Unknown')}\n"
            progress_text += f"- Total Progress: {summary.get('completedLessons', 0)}/{summary.get('totalLessons', 0)} lessons ({summary.get('completionPercent', 0)}%)\n"
            
            if next_lesson:
                progress_text += f"- Recommended Next Lesson: '{next_lesson.get('lessonTitle')}' (Unit: {next_lesson.get('moduleTitle')})\n"
            
            recent = summary.get('recentLessons', [])
            if recent:
                progress_text += "- Recent Activity:\n"
                for item in recent:
                    status = "Completed" if item.get('completed') else "In Progress"
                    progress_text += f"  * {item.get('lessonTitle')} ({item.get('moduleTitle')}): {status}\n"
            
            return progress_text
        else:
            print(f"   ⚠️ Could not fetch progress (Status {resp.status_code}).")
            return "No progress data available."
    except Exception as e:
        print(f"   💥 Connection Error: {e}")
        return "Error fetching progress."

def get_rag_context(token_string):
    """Combines Lessons + User Stats into one Context String."""
    lessons = fetch_all_lessons(token_string)
    progress_summary = fetch_user_progress(token_string)
    
    context_str = "\n--- SYSTEM CONTEXT (RAG DATA) ---\n"
    
    # 1. Add User Specifics (High Priority)
    if progress_summary:
        context_str += f"{progress_summary}\n"

    # 2. Add Available Curriculum (Truncated to save context)
    if lessons:
        context_str += "AVAILABLE CURRICULUM:\n"
        # We limit to 40 lessons to avoid hitting token limits
        context_str += "\n".join(lessons[:40]) 
        if len(lessons) > 40: 
            context_str += f"\n...and {len(lessons)-40} more lessons."
        context_str += "\n"
        
    context_str += "--- END OF CONTEXT ---\n"
    context_str += "INSTRUCTION: You are a tutor for VistaSL. Use the Student Profile above to personalize your advice. If they ask 'what should I do next?', refer to the 'Recommended Next Lesson'.\n"
    
    return context_str