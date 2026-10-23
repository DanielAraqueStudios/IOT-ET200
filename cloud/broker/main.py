from contextlib import asynccontextmanager
from fastapi import FastAPI
import os

from auth import check_device_token
from broker import MqttBroker

_broker = MqttBroker()
_broker.auth_callback = check_device_token

MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))


@asynccontextmanager
async def lifespan(app: FastAPI):
    server = await _broker.start(port=MQTT_PORT)
    yield
    server.close()


# Separate ASGI app: Railway's HTTP $PORT only serves a health check here —
# the actual MQTT traffic goes over MQTT_PORT via Railway's TCP Proxy
# (see README.md). This process runs both in the same event loop.
app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"mqtt": True, "mqtt_port": MQTT_PORT}
