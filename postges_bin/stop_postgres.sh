#!/bin/bash
PG_DIR="$HOME/postgres"
DATA_DIR="$HOME/postgres_data"

export PATH="$PG_DIR/bin:$PATH"

echo "🛑 Stopping PostgreSQL..."
pg_ctl -D "$DATA_DIR" stop
echo "✅ Server stopped."
