# Wolfee Analytics — FastAPI backend that also serves the static frontend
# (same origin; see docs/agents/DEPLOYMENT.md §6). Built by `fly deploy`.
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Fully pinned, hash-checked dependency set (generated from backend/requirements.txt).
COPY backend/requirements.lock backend/requirements.lock
RUN pip install --require-hashes -r backend/requirements.lock

COPY backend backend
COPY frontend frontend

RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

# main.py serves ../frontend at "/", and the release command runs from here.
WORKDIR /app/backend

EXPOSE 8080
# No --proxy-headers / --forwarded-allow-ips: the client IP comes from Fly-Client-IP
# (security_middleware.get_client_ip, REQ-39) and HTTPS is detected from COOKIE_SECURE /
# X-Forwarded-Proto there, so uvicorn must not rewrite the peer from client-supplied headers.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
