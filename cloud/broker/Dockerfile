FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Railway injects $PORT for the HTTP health check; uvicorn must bind to
# it, not a hardcoded port. The MQTT listener binds MQTT_PORT separately
# and is reached through Railway's TCP Proxy, not $PORT — see README.md.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
