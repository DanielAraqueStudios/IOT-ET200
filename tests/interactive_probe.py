"""Interactive MQTT probe — a manual stand-in for the PLC/edge gateway.

test_smoke.py is an automated pass/fail check on a throwaway topic.
This script is for root-causing a real failure: it connects to the
broker on the SAME topics edge/small_scope actually uses
(plant/small_scope/output/state, plant/small_scope/input/state) and
lets you type a value at the terminal to publish it yourself, while
printing everything it receives live.

Why this helps isolate the fault: if the dashboard isn't showing
updates, you can't tell from the dashboard alone whether the PLC, the
gateway, the broker, or the dashboard's own ingest is at fault. Run
this probe and publish a value by hand:

  - Broker relays it / dashboard's /api/state picks it up
      -> broker and dashboard are fine; look at the PLC or
         edge/small_scope gateway (OPC UA side), not the cloud half.
  - Broker relays it but the dashboard never shows it
      -> look at cloud/dashboard/backend's mqtt_ingest, not the broker.
  - This probe itself never sees its own publish come back on a
    second probe / another subscriber
      -> the broker itself is the fault, independent of the PLC.

Usage:
    python tests/interactive_probe.py

Configuration (env vars, same names as test_smoke.py so one
scripts/.local-stack/local.env-derived setup works for both):

    MQTT_HOST              default: localhost
    MQTT_PORT              default: 18830
    MQTT_TLS_CA_CERT       path to the broker's cert (required)
    MQTT_USERNAME          device-token username
    MQTT_DEVICE_TOKEN      the matching device token (password)
    MQTT_OUTPUT_TOPIC      default: plant/small_scope/output/state (what the PLC publishes)
    MQTT_INPUT_TOPIC       default: plant/small_scope/input/state  (what the dashboard/gateway publishes back)

At the prompt, type either:
    <value>                 publish <value> to MQTT_OUTPUT_TOPIC (imitates the PLC)
    <topic> <value>         publish <value> to an explicit topic
    quit / exit / Ctrl+C    disconnect and exit
"""
import os
import ssl
import sys
import threading
import time

import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "18830"))
CERT = os.environ.get("MQTT_TLS_CA_CERT")
USERNAME = os.environ.get("MQTT_USERNAME", "test@example.com")
PASSWORD = os.environ.get("MQTT_DEVICE_TOKEN", "testtoken123")
OUTPUT_TOPIC = os.environ.get("MQTT_OUTPUT_TOPIC", "plant/small_scope/output/state")
INPUT_TOPIC = os.environ.get("MQTT_INPUT_TOPIC", "plant/small_scope/input/state")

if not CERT:
    print("FAIL: MQTT_TLS_CA_CERT must point at the broker's TLS cert (see README.md)")
    sys.exit(1)

_print_lock = threading.Lock()


def on_connect(client, userdata, flags, reason_code, properties=None):
    with _print_lock:
        print(f"[probe] connected, rc={reason_code}")
    for topic in (OUTPUT_TOPIC, INPUT_TOPIC):
        client.subscribe(topic)
        with _print_lock:
            print(f"[probe] subscribed: {topic}")


def on_message(client, userdata, msg):
    with _print_lock:
        print(f"\n[RECEIVED] {msg.topic} = {msg.payload.decode(errors='replace')!r}\n> ", end="", flush=True)


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="interactive-probe", protocol=mqtt.MQTTv311)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(ca_certs=CERT, cert_reqs=ssl.CERT_REQUIRED)
    client.tls_insecure_set(True)  # self-signed cert, pinned via ca_certs above
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(HOST, PORT, keepalive=30)
    client.loop_start()
    time.sleep(1)

    print(f"Connected to mqtts://{HOST}:{PORT} as {USERNAME!r}.")
    print(f"Default publish topic (imitates the PLC/gateway): {OUTPUT_TOPIC}")
    print("Type a value to publish, 'topic value' for an explicit topic, or 'quit' to exit.\n")

    try:
        while True:
            line = input("> ").strip()
            if not line:
                continue
            if line.lower() in ("quit", "exit"):
                break
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and "/" in parts[0]:
                topic, value = parts
            else:
                topic, value = OUTPUT_TOPIC, line
            client.publish(topic, value)
            print(f"[SENT] {topic} = {value!r}")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        print("\n[probe] disconnected.")


if __name__ == "__main__":
    main()
