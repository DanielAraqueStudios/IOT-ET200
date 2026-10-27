"""MQTT pub/sub smoke test against a running broker instance.

Connects two MQTT clients over TLS (one subscriber, one publisher), confirms
a message round-trips between them, and confirms that wrong device-token
credentials are rejected with a bad-username/password CONNACK.

Run against a broker started via `python scripts/run_local_stack.py up` or
Docker (see README.md "Running the MQTT smoke test" for the full setup).
Not collected by a generic `pytest` run across the repo; run it explicitly:

    python tests/test_smoke.py

Configuration (env vars, all optional — defaults target a local broker):

    MQTT_HOST              default: localhost
    MQTT_PORT              default: 18830
    MQTT_TLS_CA_CERT       path to the broker's cert (required — no default,
                            since there's no safe cert to assume is present)
    MQTT_USERNAME           device-token username to authenticate with
    MQTT_DEVICE_TOKEN       the matching device token (password)
    MQTT_TEST_TOPIC          default: plant/smoke/test (must start with the
                              broker's MQTT_TOPIC_PREFIX, default "plant/",
                              or the broker's topic ACL will reject it)
"""
import os
import ssl
import sys
import time

import paho.mqtt.client as mqtt

HOST = os.environ.get("MQTT_HOST", "localhost")
PORT = int(os.environ.get("MQTT_PORT", "18830"))
CERT = os.environ.get("MQTT_TLS_CA_CERT")
USERNAME = os.environ.get("MQTT_USERNAME", "test@example.com")
PASSWORD = os.environ.get("MQTT_DEVICE_TOKEN", "testtoken123")
TOPIC = os.environ.get("MQTT_TEST_TOPIC", "plant/smoke/test")
PAYLOAD = b"hello-from-smoke-test"

if not CERT:
    print("FAIL: MQTT_TLS_CA_CERT must point at the broker's TLS cert (see README.md)")
    sys.exit(1)


def make_client(name, username=USERNAME, password=PASSWORD):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=name, protocol=mqtt.MQTTv311)
    c.username_pw_set(username, password)
    c.tls_set(ca_certs=CERT, cert_reqs=ssl.CERT_REQUIRED)
    c.tls_insecure_set(True)  # self-signed cert, CN=localhost, pinned via ca_certs above
    return c


def run_pubsub_roundtrip():
    received = {}
    connect_results = {}

    def on_connect_sub(client, userdata, flags, reason_code, properties=None):
        connect_results["sub"] = reason_code
        print(f"[sub] CONNACK rc={reason_code}")
        client.subscribe(TOPIC)

    def on_message(client, userdata, msg):
        print(f"[sub] received on {msg.topic}: {msg.payload!r}")
        received["topic"] = msg.topic
        received["payload"] = msg.payload

    def on_connect_pub(client, userdata, flags, reason_code, properties=None):
        connect_results["pub"] = reason_code
        print(f"[pub] CONNACK rc={reason_code}")

    sub = make_client("smoke-sub")
    sub.on_connect = on_connect_sub
    sub.on_message = on_message
    sub.connect(HOST, PORT, keepalive=10)
    sub.loop_start()

    time.sleep(1)  # let SUBSCRIBE land before anyone publishes

    pub = make_client("smoke-pub")
    pub.on_connect = on_connect_pub
    pub.connect(HOST, PORT, keepalive=10)
    pub.loop_start()

    time.sleep(1)
    pub.publish(TOPIC, PAYLOAD)

    start = time.time()
    while "payload" not in received and time.time() - start < 10:
        time.sleep(0.2)

    sub.loop_stop()
    pub.loop_stop()
    sub.disconnect()
    pub.disconnect()

    if connect_results.get("sub") != 0 or connect_results.get("pub") != 0:
        print(f"FAIL: auth/connect rejected, results={connect_results}")
        return False

    if received.get("payload") == PAYLOAD and received.get("topic") == TOPIC:
        print("PASS: connect + auth + pub/sub round-trip succeeded")
        return True

    print(f"FAIL: did not receive expected message, got {received}")
    return False


def run_bad_credentials_rejected():
    connect_results = {}

    def on_connect(client, userdata, flags, reason_code, properties=None):
        connect_results["rc"] = reason_code
        print(f"[bad-auth] CONNACK rc={reason_code}")

    client = make_client("smoke-bad-auth", username=USERNAME, password=PASSWORD + "-wrong")
    client.on_connect = on_connect
    client.connect(HOST, PORT, keepalive=10)
    client.loop_start()

    start = time.time()
    while "rc" not in connect_results and time.time() - start < 10:
        time.sleep(0.2)

    client.loop_stop()
    client.disconnect()

    rc = connect_results.get("rc")
    # paho's v2 callback API reports CONNACK rejections as a ReasonCode
    # object (not the raw MQTTv3.1.1 integer 4), so check failure + name
    # rather than a hardcoded numeric code.
    if rc is not None and rc.is_failure and "user name" in rc.getName().lower():
        print(f"PASS: wrong device-token credentials were rejected ({rc.getName()})")
        return True

    print(f"FAIL: expected a bad-username/password CONNACK rejection, got rc={rc}")
    return False


if __name__ == "__main__":
    ok = run_pubsub_roundtrip()
    ok = run_bad_credentials_rejected() and ok
    sys.exit(0 if ok else 1)
