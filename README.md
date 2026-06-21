# VISTA-SL LLM Middleware Service

The **VISTA-SL LLM Backend** is a modular middleware service built with FastAPI. It leverages **LiteLLM** for universal LLM provider support (Groq, Together AI, OpenAI, etc.), provides **Retrieval-Augmented Generation (RAG)** using the local sign language curriculum, and logs user chat histories in a PostgreSQL database.

---

## 🚀 Getting Started with Docker (Recommended)

Docker Compose orchestrates both the **FastAPI Middleware Backend** and the **PostgreSQL Database** container.

### Prerequisites
Make sure you have [Docker](https://docs.docker.com/) and [Docker Compose](https://docs.docker.com/compose/) installed on your machine.

### Setup Instructions

1. **Clone & Configure Environment Variables**:
   Copy the sample environment file to create your own configuration:
   ```bash
   cp .env.example .env
   ```
   Open the `.env` file and input your credentials, including your **LLM provider API key** (e.g., `GROQ_API_KEY`).

2. **Start the Services**:
   Launch the system using Docker Compose:
   ```bash
   docker compose up --build -d
   ```
   This will:
   - Build the backend application container.
   - Start the PostgreSQL database container and initialize tables (`chat_messages` and `user_threads`).
   - Automatically mount volumes for database persistence (`postgres_data`) and vector stores (`chroma_data`).

3. **Check Running Containers & Logs**:
   To monitor the logs and ensure startup runs without errors:
   ```bash
   docker compose logs -f
   ```

4. **Shutdown Services**:
   To stop and tear down the containers (preserving persistent database volumes):
   ```bash
   docker compose down
   ```

---

## 🛠️ Local/Development Execution

If you prefer to run the service locally outside of Docker, follow these steps:

### Prerequisites
- Python 3.10 or newer
- PostgreSQL running locally

### Local Setup Instructions

1. **Setup Database**:
   Create a database (e.g., `vista_db`) in your local Postgres server.
   
2. **Install Dependencies**:
   Initialize and sync dependencies using `uv` (or standard `pip`):
   ```bash
   uv pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file from `.env.example` and set `DATABASE_URL` to point to your local PostgreSQL instance:
   ```env
   DATABASE_URL=postgresql://<username>:<password>@localhost:5432/<db_name>
   ```

4. **Run Application**:
   Start the FastAPI server:
   ```bash
   python backend/main.py
   ```
   The API will be available at `http://localhost:8000`.

---

## 📋 System Features

- **Universal LLM Adapter**: Powered by LiteLLM. Easily switch model providers via the `LLM_MODEL` variable in `.env` without changing code.
- **Dynamic RAG Engine**: On startup, the system parses [curriculum/curriculum.txt](file:///home/animal/Desktop/vista_sl_llm/curriculum/curriculum.txt) dynamically, preparing standard lessons to inject contextually into the LLM prompt based on query similarity.
- **SQL Chat Logging**: User chats are stored in SQL tables. Chat endpoints automatically retrieve recent conversation histories for continuous conversational memory.

---

## 🛠️ CLI Admin Tools

An [admin_tools.py](file:///home/animal/Desktop/vista_sl_llm/admin_tools.py) utility is provided to manage the database chat records and users directly. Run it within your virtual environment:

### List Active Users and Logs
View the list of users, their total chat message counts, and when they were last active:
```bash
python admin_tools.py list
```

### Delete User Chat History
Purge history and legacy threads for a specific user:
```bash
python admin_tools.py delete <user_id>
```

### Wipe All Database Chat Data
Permanently clear all chat messages and legacy logs (requires CLI user confirmation):
```bash
python admin_tools.py wipe_logs
```
