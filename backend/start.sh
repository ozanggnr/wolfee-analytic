#!/bin/bash
echo "Starting Wolfee Analytics on Railway..."

# Run Alembic migrations if configured, with graceful fallback to main.py lifespan create_all
alembic upgrade head || echo "Alembic migrations completed or handled by database init_db"

# Start FastAPI server with proxy headers enabled for Railway reverse proxy
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"
