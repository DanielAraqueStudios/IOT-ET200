FROM python:3.12-slim

# Unbuffered stdout: print()'d log lines (ours and asyncio's) would
# otherwise sit in Python's block buffer — since stdout isn't a TTY here —
# and flush out of order relative to uvicorn's own logging-module output,
# making the deploy log timeline misleading when diagnosing crashes.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Node.js is needed only to run the Prisma CLI for migrations — the
# service itself runs on Python/FastAPI (see main.py). Prisma is used
# purely as a schema/migration tool here, not as the runtime client.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY package.json .
RUN npm install --omit=dev=false

COPY . .

# This service also runs a TCP Proxy (for MQTT), and Railway ties its
# injected $PORT to that proxy's target port (MQTT_PORT, 1883) rather
# than the HTTP domain's target port — so uvicorn binding $PORT would
# collide with our own MQTT listener binding MQTT_PORT in the same
# process. Bind uvicorn to a fixed HTTP_PORT instead, matching Settings
# → Networking → Public Networking → Target port (see README.md).
# `prisma migrate deploy` applies any pending migrations against
# DATABASE_URL before the app starts (Prisma's recommended deploy-time
# migration step; see README.md "Database migrations").
#
# `exec` before uvicorn replaces the shell (PID 1) with the uvicorn
# process itself, instead of leaving uvicorn as a child of `sh`. Without
# it, a restart's SIGTERM goes to the shell, which doesn't forward it to
# uvicorn — the old process lingers holding MQTT_PORT while the new
# container's uvicorn tries to bind the same port, crash-looping on
# "address already in use".
CMD ["sh", "-c", "npx prisma migrate deploy && exec uvicorn main:app --host 0.0.0.0 --port ${HTTP_PORT:-8080}"]
