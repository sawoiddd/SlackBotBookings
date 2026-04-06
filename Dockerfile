FROM python:3.13-slim

# Prevent .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- Dependencies layer (cached unless requirements.txt changes) -----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Non-root user ---------------------------------------------------------
RUN addgroup --system bot && adduser --system --ingroup bot bot
USER bot

# --- Application code ------------------------------------------------------
COPY . .

# Tell Docker to send SIGTERM (which main.py now handles) for graceful shutdown.
STOPSIGNAL SIGTERM

# Lightweight liveness probe: verify the Python process is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os, signal; os.kill(1, 0)"]

# Socket Mode is outbound-only WebSocket — no ports to expose.
CMD ["python", "main.py"]

