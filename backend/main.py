from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os

# Backend imports
from backend.logging_config import setup_logging
setup_logging()

from backend import database, rag_engine
from backend.routes import chat_router, health_router

app = FastAPI(title="VISTA-SL LLM Backend")

@app.on_event("startup")
def startup_event():
    database.init_db()
    rag_engine.init_rag()

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(chat_router)
app.include_router(health_router)

if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
