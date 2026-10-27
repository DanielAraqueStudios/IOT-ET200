"""Subscribes to the gateway's output/input state topics over MQTT TLS
and writes every change into plc_state. Runs in a background thread
started from main.py.

Auth: the Paint-mixer broker's `check_device_token(email, token)` (see
`api/auth.py` in that repo) validates the MQTT CONNECT packet's
username/password fields directly — username = account email, password
= that account's device token (from `GET /api/auth/device-token`).
There is no separate header or MQTT property for this; it rides the
standard CONNECT username/password fields. TLS is on top of this, not
instead of it (defense in depth) — the broker still requires both.

TLS: the broker uses a self-signed cert, trusted manually rather than
through a public CA (same posture as this project's OPC UA leg, which
already runs with endpointMustExist:false). Point MQTT_TLS_CA_CERT at
a local copy of that exact cert (fetch it once, e.g. with
`openssl s_client -connect <host>:<port> -showcerts`, and save the
server's certificate PEM) so paho validates against it specifically,
instead of the public CA trust store (which a self-signed cert will
always fail).
"""
import os
import tempfile

import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session

from models import engine, PlcState

# Tracks this backend's own MQTT connection state (set by the on_connect/
# on_disconnect callbacks below) — reported by GET /api/health as the
# "broker" signal, since it reflects whether *this backend* can actually
# reach the broker, not just whether the broker process is up.
_connected = False


def is_connected() -> bool:
    return _connected

MQTT_URL = os.environ["MQTT_URL"]  # e.g. mqtts://your-app.up.railway.app:1884
MQTT_USERNAME = os.environ["MQTT_USERNAME"]  # account email registered with the broker
MQTT_DEVICE_TOKEN = os.environ["MQTT_DEVICE_TOKEN"]  # from GET /api/auth/device-token
MQTT_TLS_CA_CERT = os.environ.get("MQTT_TLS_CA_CERT")  # path to the broker's self-signed cert PEM, OR the PEM content itself
TOPICS = [
    os.environ.get("MQTT_OUTPUT_TOPIC", "plant/small_scope/output/state"),
    os.environ.get("MQTT_INPUT_TOPIC", "plant/small_scope/input/state"),
]


def _parse_url(url: str):
    # mqtts://host:port -> (host, port)
    rest = url.split("://", 1)[1]
    host, port = rest.split(":")
    return host, int(port)


def _on_connect(client, userdata, flags, rc):
    global _connected
    _connected = rc == 0
    print(f"[mqtt_ingest] connected, rc={rc}")
    for topic in TOPICS:
        client.subscribe(topic)
        print(f"[mqtt_ingest] subscribed: {topic}")


def _on_disconnect(client, userdata, rc):
    global _connected
    _connected = False
    print(f"[mqtt_ingest] disconnected, rc={rc}")


def _on_message(client, userdata, msg):
    tag_name = msg.topic
    value = msg.payload.decode(errors="replace")
    with Session(engine) as s:
        s.add(PlcState(tag_name=tag_name, value=value))
        s.commit()
    print(f"[mqtt_ingest] {tag_name} = {value}")


def start():
    host, port = _parse_url(MQTT_URL)
    client = mqtt.Client(protocol=mqtt.MQTTv311)
    client.username_pw_set(MQTT_USERNAME, MQTT_DEVICE_TOKEN)
    if MQTT_TLS_CA_CERT:
        # Pin the broker's own self-signed cert as the trust anchor,
        # since it isn't CA-issued and the public trust store will
        # always reject it. paho's tls_set only accepts a file path —
        # on a cloud host with no shared filesystem (e.g. Railway),
        # MQTT_TLS_CA_CERT holds the PEM content itself (same Shared
        # Variable the broker loads as MQTT_TLS_CERT), so write it to
        # a throwaway file first.
        ca_cert_path = MQTT_TLS_CA_CERT
        if MQTT_TLS_CA_CERT.lstrip().startswith("-----BEGIN"):
            fd, ca_cert_path = tempfile.mkstemp(suffix=".crt")
            with os.fdopen(fd, "w") as f:
                f.write(MQTT_TLS_CA_CERT)
        client.tls_set(ca_certs=ca_cert_path)
    else:
        print("[mqtt_ingest] WARNING: MQTT_TLS_CA_CERT not set — "
              "falling back to no certificate validation (insecure, "
              "lab/POC only). Set it to the broker's self-signed cert "
              "PEM to validate properly.")
        client.tls_set()
        client.tls_insecure_set(True)
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.connect(host, port, keepalive=60)
    client.loop_start()
    return client
