import asyncio
import os
import sys

# Ensure we can import local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.llm_service import stream_chat

async def run_full_context_test():
    curriculum_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "curriculum", "curriculum.txt"))
    
    if not os.path.exists(curriculum_path):
        print(f"❌ Error: Curriculum file not found at: {curriculum_path}")
        return

    # 1. LOAD THE ENTIRE CURRICULUM FILE
    with open(curriculum_path, "r", encoding="utf-8") as f:
        full_curriculum_text = f.read()

    # 2. Setup DUMMY PROGRESS (First 3 lessons finished)
    dummy_stats = """
STUDENT PROFILE:
- Username: Alexandros
- LESSONS FINISHED: Lesson 1 (Α), Lesson 2 (Β), Lesson 3 (Γ)
- CURRENT STATUS: Finished Unit 1: The Alphabet basics.
    """

    user_message = "I've finished the first three letters. Briefly tell me what the next 2 lessons are and give me their video links."

    # 3. BUILD THE RAW PROMPT (Stuffing the WHOLE file in)
    system_prompt = f"""You are the VISTA-SL AI Coach. 
You have access to the ENTIRE curriculum below. Use it to guide the student based on their progress.

--- COMPLETE CURRICULUM ---
{full_curriculum_text}
--- END OF CURRICULUM ---

--- STUDENT PROGRESS ---
{dummy_stats}

INSTRUCTIONS:
- Identify the next lessons in sequence after the finished ones.
- Provide the title and the exact video link from the curriculum for each.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    print(f"📦 Stuffed {len(full_curriculum_text)} characters of curriculum into prompt.")
    print("🚀 Calling Groq with FULL context...")

    print("\n🤖 COACH RESPONSE:\n")
    print("-" * 30)
    async for chunk in stream_chat(messages):
        print(chunk, end="", flush=True)
    print("\n" + "-" * 30)

if __name__ == "__main__":
    asyncio.run(run_full_context_test())
