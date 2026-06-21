import os
import asyncio
import sys

# Fix pathing to import from the root directory
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from backend.llm_service import upload_document, update_embeddings

# Config - Use the newly extracted curriculum.txt
KB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "curriculum.txt")

async def run_sync():
    print(f"📤 Step 1: Uploading '{os.path.basename(KB_FILE)}' to AnythingLLM via API...")
    
    if not os.path.exists(KB_FILE):
        print(f"❌ Error: {KB_FILE} not found. Please run your parsing script first.")
        return

    doc_location = await upload_document(KB_FILE)
    
    if not doc_location:
        print("❌ Upload failed. Ensure AnythingLLM is running and the API key is correct.")
        return

    print(f"✅ Uploaded successfully: {doc_location}")
    
    print("🧠 Step 2: Triggering Vector Embedding (Save & Embed)...")
    success = await update_embeddings(doc_location)
    
    if success:
        print("🎉 SUCCESS! Your LLM is now trained on the latest curriculum.")
    else:
        print("❌ Failed to update embeddings. Check AnythingLLM logs.")

if __name__ == "__main__":
    asyncio.run(run_sync())