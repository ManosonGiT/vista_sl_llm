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
   Open the `.env` file and input your credentials, including your **LLM provider API key** (e.g., `GROQ_API_KEY`), and configure any **Backup LLM** or **Rate Limiting** variables.

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
   To stop and tear down the containers (preserving database volumes):
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

- **Universal LLM Adapter**: Powered by LiteLLM. Switch model providers via the `LLM_MODEL` variable in `.env` without changing code.
- **RAG Engine**: On startup, the system parses [curriculum/curriculum.txt](file:///home/animal/Desktop/vista_sl_llm/curriculum/curriculum.txt) dynamically, preparing standard lessons to inject contextually into the LLM prompt based on query similarity.
- **SQL Chat Logging**: User chats are stored in SQL tables. Chat endpoints automatically retrieve recent conversation histories for continuous conversational memory.

### 🛡️ Production & Reliability Features

1. **🔒 Database Network Isolation (Port Security)**:
   - For security, Postgres ports are commented out in `docker-compose.yml` to prevent public DB exposure.
   - If running local test scripts outside Docker, temporarily uncomment the database `ports` mapping in `docker-compose.yml` and rebuild the container.
2. **🧠 LLM Fallback (Backup Provider)**:
   - If the primary provider (e.g., Groq) fails due to rate limits or invalid keys, the app attempts fallback completions via variables `BACKUP_LLM_MODEL`, `BACKUP_LLM_API_KEY`, and `BACKUP_LLM_API_BASE`.
3. **⏳ User Chat History TTL**:
   - In-app TTL cleans up user history in [backend/database.py](file:///home/animal/Desktop/vista_sl_llm/backend/database.py). Wipes a user's messages if they haven't chatted in 1 hour, and limits session memory to messages from the last hour.
4. **🚦 Rate Limiting**:
   - Implements a sliding window in-memory rate limiter in [backend/rate_limiter.py](file:///home/animal/Desktop/vista_sl_llm/backend/rate_limiter.py) preventing request spam. Thresholds are controlled via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW`.
5. **📝 Structured Logging**:
   - Uses unified logging format ([backend/logging_config.py](file:///home/animal/Desktop/vista_sl_llm/backend/logging_config.py)) replacing unformatted terminal print statements.

---

## 🛠️ CLI Admin Tools

An [admin_tools.py](file:///home/animal/Desktop/vista_sl_llm/admin_tools.py) utility is provided to manage database chat records and users directly. Run it within your virtual environment:

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

---

## 🧪 Testing

The repository contains unit and integration tests under the `tests/` directory:

### Running Integration & Flow Tests (Host side)
Make sure the docker containers are running (`docker compose up -d`), then execute the following on the host machine using your virtual environment:

1. **End-to-End Chat Flow & Session Token Test**:
   Tests streaming chat completion, RAG search context injection, conversation memory recall, and session token fetching from the platform:
   ```bash
   .venv/bin/python tests/test_history_flow.py
   ```

2. **Rate Limiting Test**:
   Sends rapid requests to verify that the HTTP 429 status code is correctly returned when thresholds are exceeded:
   ```bash
   .venv/bin/python tests/test_rate_limit.py
   ```

3. **HMAC Hashing Test**:
   Verifies that the HMAC signature headers are generated correctly using SHA-256 and the coach secret key:
   ```bash
   .venv/bin/python tests/test_hashing.py
   ```

4. **Production Diagnostic Checks**:
   Executes the diagnostic tool checking backend online status, database health, LLM connection, and platform session validation:
   ```bash
   .venv/bin/python tests/test_diagnostic.py
   ```

### Running Database-dependent Tests in Docker
Because Postgres ports are isolated inside the Docker network, tests that connect directly to the database (like TTL memory expiration or internal coach routing) should be executed inside a network-connected container:

1. **Chat History TTL Expiration Test**:
   ```bash
   docker run --runtime runc --rm -v $(pwd):/app -w /app --network vista_sl_llm_default --env-file .env -e DATABASE_URL=postgresql://lionakis:TempPass@db:5432/vista_db vista_sl_llm-vista-backend python tests/test_ttl.py
   ```

2. **Coach Intelligence & Next-Lesson Routing Test**:
   ```bash
   docker run --runtime runc --rm -v $(pwd):/app -w /app --network vista_sl_llm_default --env-file .env -e DATABASE_URL=postgresql://lionakis:TempPass@db:5432/vista_db vista_sl_llm-vista-backend python tests/test_coach_logic.py
   ```
