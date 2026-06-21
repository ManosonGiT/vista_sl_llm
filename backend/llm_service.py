"""
LLM Service — Powered by LiteLLM for universal provider support.

Allows easy switching between Groq, TogetherAI, OpenAI, etc.,
providing redundancy and cost optimization.
"""

import os
import json
import litellm
from litellm import completion
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("LLM_MODEL")
if not DEFAULT_MODEL:
    raise ValueError("LLM_MODEL environment variable must be set!")

# Silence diagnostic logs from litellm
litellm.set_verbose = False

async def stream_chat(messages: list[dict], model_override: str = None):
    """
    Stream a chat completion using LiteLLM.
    """
    model = model_override or DEFAULT_MODEL
    
    try:
        # LiteLLM automatically picks up API keys from .env 
        # (e.g., GROQ_API_KEY, OPENAI_API_KEY)
        response = completion(
            model=model,
            messages=messages,
            stream=True,
            temperature=0.7,
            max_tokens=1024
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        print(f"💥 LiteLLM Error: {e}")
        yield f"[Error: LLM Provider ({model}) returned an error. Check your API keys.]"

async def check_connection() -> bool:
    """
    Simple health check for the configured provider.
    """
    try:
        # Just a tiny call to verify the key
        completion(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5
        )
        return True
    except Exception:
        return False
