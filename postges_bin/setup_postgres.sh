#!/bin/bash

# --- CONFIGURATION ---
PG_VERSION="14.10" # Standard stable version
PG_DIR="$HOME/postgres"
DATA_DIR="$HOME/postgres_data"
PORT=5433
DB_NAME="vistasl_db"
USER_NAME=$(whoami)

echo "🚀 Starting Local PostgreSQL Setup (No Sudo)..."

# 1. Download and Extract (if not exists)
if [ ! -d "$PG_DIR" ]; then
    echo "⬇️  Downloading PostgreSQL binaries..."
    # EnterpriseDB binaries for Linux x86-64
    wget -q https://get.enterprisedb.com/postgresql/postgresql-$PG_VERSION-1-linux-x64-binaries.tar.gz -O postgres.tar.gz
    
    echo "📦 Extracting..."
    tar -xzf postgres.tar.gz
    mv pgsql $PG_DIR
    rm postgres.tar.gz
    echo "✅ Installed to $PG_DIR"
else
    echo "✅ PostgreSQL already installed at $PG_DIR"
fi

# 2. Add to Path temporarily
export PATH="$PG_DIR/bin:$PATH"
export LD_LIBRARY_PATH="$PG_DIR/lib:$LD_LIBRARY_PATH"

# 3. Initialize Data Directory
if [ ! -d "$DATA_DIR" ]; then
    echo "📂 Initializing Database Cluster at $DATA_DIR..."
    initdb -D "$DATA_DIR" -U "$USER_NAME" --auth=trust > /dev/null
    echo "✅ Database initialized."
else
    echo "✅ Data directory exists."
fi

# 4. Start Server
if pg_isready -p $PORT > /dev/null 2>&1; then
    echo "✅ Server is already running on port $PORT"
else
    echo "🔌 Starting PostgreSQL Server on port $PORT..."
    # Start in background, log to postgres.log
    pg_ctl -D "$DATA_DIR" -l postgres.log -o "-p $PORT" start
    sleep 3 # Wait for startup
    echo "✅ Server started."
fi

# 5. Create Database
if psql -p $PORT -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    echo "✅ Database '$DB_NAME' already exists."
else
    echo "🔨 Creating database '$DB_NAME'..."
    createdb -p $PORT "$DB_NAME"
    echo "✅ Database created."
fi

echo "============================================"
echo "🎉 SUCCESS! Postgres is running on port $PORT"
echo "👉 Connection String: postgresql://$USER_NAME@localhost:$PORT/$DB_NAME"
echo "============================================"
