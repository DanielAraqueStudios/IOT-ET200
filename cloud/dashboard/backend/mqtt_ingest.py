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

# The paho client instance set by start(), used by publish() below. Module-
# level rather than returned-and-threaded-through, matching how `_connected`
# is already tracked here (main.py only ever holds one of these).
_client = None


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


def publish(topic: str, payload: str) -> None:
    """Publishes to the broker over this module's already-connected paho
    client (same connection used for the subscribe-only ingest above).
    Raises RuntimeError if there's no connected client to publish with —
    callers (main.py) should check is_connected() first and surface a
    clear error rather than relying on this to fail loudly after the
    fact, but this is a backstop either way. The broker's own ACL (see
    cloud/broker/broker.py _publish_allowed) separately requires this
    client's identity to have can_command=True for a `/command` topic —
    a rejected publish here still returns immediately (paho's publish()
    doesn't surface broker-side ACL rejections synchronously), so this
    only catches "not connected", not "connected but not authorized"."""
    if _client is None or not is_connected():
        raise RuntimeError("MQTT client is not connected — cannot publish")
    info = _client.publish(topic, payload)
    info.wait_for_publish(timeout=5)


def start():
    global _client
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
    _client = client
    return client
