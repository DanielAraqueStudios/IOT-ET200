FROM python:3.12-slim

# Unbuffered stdout so mqtt_ingest's connect/subscribe prints show up
# promptly in Railway's deploy logs instead of sitting in Python's
# block buffer (stdout isn't a TTY in a container).
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Railway injects $PORT; uvicorn must bind to it, not a hardcoded port.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
