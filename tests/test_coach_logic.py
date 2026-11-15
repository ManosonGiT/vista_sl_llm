import asyncio
import os
import sys

# Ensure we can import local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.rag_engine import init_rag, get_module_list, _modules, get_next_lesson_in_module
from backend.llm_service import stream_chat

async def run_intelligent_test():
    init_rag()
    
    # 1. State: Finished 24 letters
    finished_titles = ["Α", "Β", "Γ", "Δ", "Ε", "Ζ", "Η", "Θ", "Ι", "Κ", "Λ", "Μ", "Ν", "Ξ", "Ο", "Π", "Ρ", "Σ", "Τ", "Υ", "Φ", "Χ", "Ψ", "Ω"]
    
    # 2. Build Module Summaries (Sneak Peek)
    # This helps the AI "see" what is inside the Unit even if the name is wrong.
    all_modules = get_module_list()
    module_summaries = []
    for mod in all_modules:
        titles = [l['title'] for l in _modules[mod][:3]] # Get first 3 titles
        module_summaries.append(f"- {mod} (Contains words like: {', '.join(titles)})")

    user_message = "I just finished all the letters! What should I learn next?"

    # 3. Enhanced Prompt
    system_prompt = f"""You are the VISTA-SL AI Coach. 

AVAILABLE CURRICULUM:
{chr(10).join(module_summaries)}

STUDENT FINISHED:
{", ".join(finished_titles)}

INSTRUCTIONS:
1. Identify the most logical NEXT module to learn. (Look at the words inside to guess the topic!)
2. Explain WHY (e.g., 'Unit 2 seems to be about Family members').
3. Your response MUST include the tag [MODULE: NameOfModule].
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    print("\n" + "💡" * 20)
    print("--- TESTING WITH MODULE INSIGHTS ---")
    print("💡" * 20 + "\n")

    full_response = ""
    async for chunk in stream_chat(messages):
        full_response += chunk
        print(chunk, end="", flush=True)
    
    if "[MODULE:" in full_response:
        # Robust extraction: get everything between [MODULE: and ] or (
        raw_tag = full_response.split("[MODULE:")[1].split("]")[0].strip()
        module_tag = raw_tag.split("(")[0].strip() # Clean up any "(Contains...)" noise
        
        next_lesson = get_next_lesson_in_module(module_tag, finished_titles)
        if next_lesson:
            print(f"\n\n✨ AUTO-PILOT PICKED: '{next_lesson['title']}' from '{module_tag}'")
            print(f"✨ LINK: {next_lesson['link']}")

if __name__ == "__main__":
    asyncio.run(run_intelligent_test())
