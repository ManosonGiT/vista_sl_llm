import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("ANYTHING_LLM_URL")
WORKSPACE = os.getenv("WORKSPACE_SLUG")
RAW_API_KEY = os.getenv("ANYTHING_LLM_KEY", "")

# Ensure Bearer token format
AUTH_HEADER = f"Bearer {RAW_API_KEY}" if "Bearer" not in RAW_API_KEY else RAW_API_KEY
HEADERS = {"Authorization": AUTH_HEADER}

async def create_thread(user_id: str):
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE}/thread/new"
    print(f"DEBUG: Creating thread at {url}")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, headers=HEADERS, json={"name": f"User-{user_id}"}, timeout=10.0)
            if resp.status_code == 200:
                slug = resp.json().get('thread', {}).get('slug')
                print(f"DEBUG: Thread Created -> {slug}") 
                return slug
            else:
                print(f"❌ API Error {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"💥 Connection Error in create_thread: {e}")
    return None

async def stream_chat(thread_slug: str, message: str):
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE}/thread/{thread_slug}/stream-chat"
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            async with client.stream("POST", url, headers={**HEADERS, "Content-Type": "application/json"}, json={"message": message, "mode": "chat"}) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        js = line[5:].strip()
                        if js == "[DONE]": break
                        try:
                            d = json.loads(js)
                            t = d.get('token') or d.get('textResponse')
                            if t: yield t
                        except: pass
        except: yield "Error connecting to AI engine."

async def delete_thread(thread_slug: str):
    """
    Physically removes the thread and history from AnythingLLM.
    """
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE}/thread/{thread_slug}"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.delete(url, headers=HEADERS)
            return resp.status_code == 200
        except: return False



async def check_connection():
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE}"
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            return resp.status_code == 200
        except: return False
async def upload_document(file_path: str):
    """
    Uploads a physical file to AnythingLLM.
    Returns the document 'location' string needed for embedding.
    """
    url = f"{BASE_URL}/api/v1/document/upload"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return None

    async with httpx.AsyncClient() as client:
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "text/plain")}
                # Note: Do not manually set Content-Type for multipart uploads
                resp = await client.post(url, headers=HEADERS, files=files, timeout=30.0)
                
                if resp.status_code == 200:
                    data = resp.json()
                    # Path looks like: "custom-documents/curriculum.txt"
                    doc_path = data.get("documents", [{}])[0].get("location")
                    return doc_path
                print(f"❌ Upload Error: {resp.text}")
        except Exception as e:
            print(f"💥 Upload Connection Error: {e}")
    return None

async def update_embeddings(doc_location: str):
    """
    Moves the uploaded file into the Workspace's Vector Space.
    This mimics clicking 'Save and Embed'.
    """
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE}/update-embeddings"
    
    payload = {
        "adds": [doc_location],
        "deletes": [] # You could put old file paths here to clean up
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload, timeout=60.0)
            if resp.status_code == 200:
                return True
            print(f"❌ Embedding Error: {resp.text}")
        except Exception as e:
            print(f"💥 Embedding Connection Error: {e}")
    return False

async def check_connection():
    url = f"{BASE_URL}/api/v1/workspace/{WORKSPACE}"
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            resp = await client.get(url, headers=HEADERS)
            return resp.status_code == 200
        except: return False