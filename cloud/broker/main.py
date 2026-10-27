from contextlib import asynccontextmanager
from fastapi import FastAPI
import os
import sys
import traceback

from auth import check_device_token
from broker import MqttBroker

_broker = MqttBroker()
_broker.auth_callback = check_device_token

MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
print(f"[DEBUG] PORT env = {os.environ.get('PORT')!r}, MQTT_PORT resolved = {MQTT_PORT}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[DEBUG] lifespan ENTER, id(_broker)={id(_broker)}", flush=True)
    try:
        server = await _broker.start(port=MQTT_PORT)
    except Exception:
        print("[DEBUG] _broker.start() raised:", flush=True)
        traceback.print_exc(file=sys.stdout)
        raise
    try:
        yield
    finally:
        print("[DEBUG] lifespan EXIT, closing server", flush=True)
        server.close()


# Separate ASGI app: Railway's HTTP $PORT only serves a health check here —
# the actual MQTT traffic goes over MQTT_PORT via Railway's TCP Proxy
# (see README.md). This process runs both in the same event loop.
app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"mqtt": True, "mqtt_port": MQTT_PORT}
