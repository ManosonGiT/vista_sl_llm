import json
import os
import asyncio
from llm_service import upload_document, update_embeddings

# Config
INPUT_JSON = os.path.join("all_lessons", "lesson_map.json")
TEMP_KB_FILE = "curriculum_knowledge_base.txt"

def build_local_txt():
    """Converts JSON to text format for the LLM."""
    if not os.path.exists(INPUT_JSON):
        return False

    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        lessons = json.load(f)

    with open(TEMP_KB_FILE, 'w', encoding='utf-8') as f:
        f.write("VISTA-SL CURRICULUM DATABASE\n\n")
        for l_id, info in lessons.items():
            f.write(f"LESSON_ID: {l_id}\nTITLE: {info['title']}\nMODULE: {info['module']}\nLINK: {info['url']}\n---\n")
    return True

async def run_sync():
    print("🔄 Step 1: Generating local knowledge base...")
    if not build_local_txt():
        print("❌ Failed to read lesson_map.json")
        return

    print("📤 Step 2: Uploading to AnythingLLM via API...")
    doc_location = await upload_document(TEMP_KB_FILE)
    
    if not doc_location:
        print("❌ Upload failed.")
        return

    print(f"✅ Uploaded successfully: {doc_location}")
    
    print("🧠 Step 3: Triggering Vector Embedding (Save & Embed)...")
    success = await update_embeddings(doc_location)
    
    if success:
        print("🎉 SUCCESS! Your LLM is now trained on the latest curriculum.")
    else:
        print("❌ Failed to update embeddings.")

if __name__ == "__main__":
    asyncio.run(run_sync())