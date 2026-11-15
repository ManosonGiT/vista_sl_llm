from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import os

# Backend imports
from backend import database, llm_service, rag_engine

router = APIRouter()

@router.get("/health")
async def health_check(db: Session = Depends(database.get_db)):
    db_status = "unhealthy"
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        print(f"💥 Healthcheck Database connection error: {e}")

    llm_connected = await llm_service.check_connection()
    llm_status = "healthy" if llm_connected else "unhealthy"
    
    # Combine statuses: if both are healthy, overall status is healthy.
    overall_status = "healthy" if (db_status == "healthy" and llm_status == "healthy") else "degraded"

    return {
        "status": overall_status,
        "database": db_status,
        "groq_api": llm_status,
        "model": os.getenv("LLM_MODEL", "groq/llama-3.1-8b-instant"),
        "provider": os.getenv("LLM_MODEL", "groq/llama-3.1-8b-instant")
    }

@router.get("/curriculum")
async def get_curriculum():
    """
    Exposes the parsed curriculum structure from the RAG engine.
    """
    return rag_engine._modules
