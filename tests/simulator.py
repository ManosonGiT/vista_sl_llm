import requests
import json
import urllib3
import os

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
BASE_URL = "https://vistasl.eelvex.net"
# NOTE: We use "signs" which was confirmed to return data
ENDPOINT = "/api/v1/game/signs" 
OUTPUT_FILE = "lesson_map.json"

# The Cookie String provided (must be fresh/active)
COOKIE_STRING = "remember_token=6|c36e1453e254f899c9d50024b94abfed26aaf18843d3d3c9bd95636be2aeb0722e9285949770949f27738187a4bc9240acc4a1c954e3e74aa41bcb4486450d7a8b; session=.eJwlzjEOwzAIQNG7eO4A2ICdy0TYgNo1aaaqd2-kzv8P71P2POJ8lu19XPEo-8vLVsZiRRTRWi0bmcxcA3J6TDIaykgIGlbddCYPCoc2TQAkma2OJRg1cGayoXLvi4B6EGRb922Qir2FLnZXadJq3L3XIQHDe7kh1xnHXyPl-wO7MC7j.aSW89A.xgstjde-aJrim1JEQbEO8WcY9Aw"

def create_lesson_map():
    """
    Fetches lesson data and saves it to lesson_map.json as a dictionary 
    keyed by lessonId.
    """
    url = f"{BASE_URL}{ENDPOINT}"
    
    print(f"🔌 Connecting to: {url}")

    headers = {
        "Cookie": COOKIE_STRING,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        
        if response.status_code == 200:
            print("✅ SUCCESS! Data retrieved.")
            
            try:
                raw_lessons = response.json()
                lesson_map = {}
                
                # Process the list into a dictionary (map) for fast lookup
                if isinstance(raw_lessons, list):
                    for lesson in raw_lessons:
                        l_id = str(lesson.get('lessonId'))
                        if l_id:
                            lesson_map[l_id] = {
                                "title": lesson.get('title'),
                                "module": lesson.get('moduleTitle'),
                                "url": f"{BASE_URL}/lesson/{l_id}"
                            }
                
                # Save the processed map to the local file
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(lesson_map, f, indent=2, ensure_ascii=False)
                
                print(f"🎉 Successfully created {OUTPUT_FILE} with {len(lesson_map)} lessons.")

            except Exception as e:
                print(f"⚠️ Received 200 OK, but failed to process JSON: {e}")
        
        else:
            print(f"❌ Error {response.status_code}: Cookie may have expired.")

    except Exception as e:
        print(f"💥 Connection Error: {e}")

if __name__ == "__main__":
    create_lesson_map()