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
from backend.logging_config import logger

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
        logger.error(f"Primary LiteLLM Error: {e}")
        
        backup_model = os.getenv("BACKUP_LLM_MODEL")
        if backup_model:
            logger.info(f"Falling back to backup LLM: {backup_model}")
            try:
                kwargs = {
                    "model": backup_model,
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.7,
                    "max_tokens": 1024
                }
                backup_api_key = os.getenv("BACKUP_LLM_API_KEY")
                backup_api_base = os.getenv("BACKUP_LLM_API_BASE")
                
                if backup_api_key:
                    kwargs["api_key"] = backup_api_key
                if backup_api_base:
                    kwargs["api_base"] = backup_api_base
                
                response = completion(**kwargs)
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as backup_err:
                logger.error(f"Backup LiteLLM Error: {backup_err}")
                yield f"[Error: Both primary ({model}) and backup ({backup_model}) LLMs failed. Primary error: {e}. Backup error: {backup_err}]"
        else:
            yield f"[Error: LLM Provider ({model}) returned an error. Check your API keys. No backup configured.]"


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
