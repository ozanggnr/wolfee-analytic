#!/bin/bash
echo "Starting Wolfee Analytics..."

# The DB tables are created via main.py lifespan event (Base.metadata.create_all).
# In a robust production environment we would run alembic here, 
# but create_all is fine for initial Railway deployment with auto-create.

# Start FastAPI server
# Render uses $PORT, Railway also uses $PORT
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
