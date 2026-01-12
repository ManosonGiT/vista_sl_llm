#!/bin/bash

# --- CONFIGURATION ---
PG_VERSION="14.1"
# The URL you requested (Source Code)
DOWNLOAD_URL="https://ftp.postgresql.org/pub/source/v$PG_VERSION/postgresql-$PG_VERSION.tar.gz"

# Folders
BASE_DIR="$HOME/postgres_build"
INSTALL_DIR="$HOME/postgres"  # Where the binaries will go
DATA_DIR="$HOME/postgres_data" # Where the DB data will go
PORT=5433
DB_NAME="vistasl_db"
USER_NAME=$(whoami)

echo "🚀 Starting Local PostgreSQL Setup (Source Build)..."
echo "ℹ️  Using Source URL: $DOWNLOAD_URL"

# 1. CLEANUP (Safety First)
# If the binary folder exists but isn't working, clear it
if [ -d "$INSTALL_DIR" ] && [ ! -f "$INSTALL_DIR/bin/initdb" ]; then
    echo "🧹 Cleaning up broken install..."
    rm -rf "$INSTALL_DIR"
fi

mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

# 2. DOWNLOAD
if [ ! -f "postgres_src.tar.gz" ]; then
    echo "⬇️  Downloading Source Code..."
    wget --no-check-certificate -O postgres_src.tar.gz "$DOWNLOAD_URL"
    
    if [ $? -ne 0 ]; then
        echo "❌ Download failed."
        exit 1
    fi
else
    echo "✅ Source archive found."
fi

# 3. EXTRACT & COMPILE
# Only compile if we haven't already installed it
if [ ! -f "$INSTALL_DIR/bin/postgres" ]; then
    echo "📦 Extracting..."
    tar -xzf postgres_src.tar.gz
    
    SRC_FOLDER="postgresql-$PG_VERSION"
    if [ ! -d "$SRC_FOLDER" ]; then
        echo "❌ Extraction failed: Folder $SRC_FOLDER not found."
        exit 1
    fi

    cd "$SRC_FOLDER"

    echo "⚙️  Configuring build..."
    # Configure to install into our local folder (No Sudo)
    ./configure --prefix="$INSTALL_DIR" --without-readline --without-zlib
    
    echo "🔨 Compiling (This might take 2-3 minutes)..."
    make -j$(nproc)

    echo "💿 Installing..."
    make install

    if [ ! -f "$INSTALL_DIR/bin/postgres" ]; then
        echo "❌ Compilation failed. Check the logs above."
        exit 1
    fi
    echo "✅ PostgreSQL Compiled and Installed to $INSTALL_DIR"
else
    echo "✅ PostgreSQL already installed at $INSTALL_DIR"
fi

# 4. SETUP ENVIRONMENT
export PATH="$INSTALL_DIR/bin:$PATH"
export LD_LIBRARY_PATH="$INSTALL_DIR/lib:$LD_LIBRARY_PATH"

# 5. INITIALIZE DATABASE
if [ ! -d "$DATA_DIR" ]; then
    echo "📂 Initializing Database Cluster..."
    initdb -D "$DATA_DIR" -U "$USER_NAME" --auth=trust > /dev/null
    echo "✅ Database initialized."
else
    echo "✅ Data directory exists."
fi

# 6. START SERVER
if pg_isready -p $PORT > /dev/null 2>&1; then
    echo "✅ Server is already running on port $PORT"
else
    echo "🔌 Starting Server on port $PORT..."
    pg_ctl -D "$DATA_DIR" -l "$BASE_DIR/postgres.log" -o "-p $PORT" start
    
    # Wait for startup
    for i in {1..5}; do
        if pg_isready -p $PORT > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    if ! pg_isready -p $PORT > /dev/null 2>&1; then
        echo "❌ Server failed to start. Check logs at $BASE_DIR/postgres.log"
        exit 1
    fi
    echo "✅ Server started."
fi

# 7. CREATE DATABASE
if psql -p $PORT -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    echo "✅ Database '$DB_NAME' already exists."
else
    echo "🔨 Creating database '$DB_NAME'..."
    createdb -p $PORT "$DB_NAME"
fi

echo "============================================"
echo "🎉 SUCCESS! Postgres is running on port $PORT"
echo "👉 Connection: postgresql://$USER_NAME@localhost:$PORT/$DB_NAME"
echo "============================================"
