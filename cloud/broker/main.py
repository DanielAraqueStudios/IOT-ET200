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


# Separate ASGI app: the HTTP health check runs on HTTP_PORT (bound by
# uvicorn's own --port, see Dockerfile) — the actual MQTT traffic goes
# over MQTT_PORT via Railway's TCP Proxy (see README.md). Railway ties
# its injected $PORT to the TCP Proxy's target port on this service, not
# the HTTP domain's, so neither uvicorn nor the broker reads $PORT
# directly; both ports are fixed via their own explicit env vars instead.
# This process runs both listeners in the same event loop.
app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"mqtt": True, "mqtt_port": MQTT_PORT}
