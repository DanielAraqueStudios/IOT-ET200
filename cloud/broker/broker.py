"""
Minimal async MQTT broker (v3.1.1).

Handles: CONNECT, PUBLISH (QoS 0/1), SUBSCRIBE, PINGREQ, DISCONNECT.
Auth via `auth_callback(username, password) -> bool`; no persistence,
no retained messages — just enough for the small_scope gateway ↔ dashboard.

Run standalone:  python broker.py
Or import and start inside FastAPI (see main.py).
"""

import asyncio
import os
import ssl
import struct
from collections import defaultdict

# ── Packet type constants ──────────────────────────────────────────────────────
CONNECT    = 1
CONNACK    = 2
PUBLISH    = 3
PUBACK     = 4
SUBSCRIBE  = 8
SUBACK     = 9
PINGREQ    = 12
PINGRESP   = 13
DISCONNECT = 14


def _encode_varlen(n: int) -> bytes:
    """Encode MQTT variable-length integer."""
    out = []
    while True:
        b = n % 128
        n //= 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


async def _read_varlen(reader: asyncio.StreamReader) -> int:
    """Decode MQTT variable-length integer from stream."""
    value, shift = 0, 0
    while True:
        b = (await reader.readexactly(1))[0]
        value |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            return value


def _read_str(buf: bytes, pos: int):
    """Read length-prefixed UTF-8 string; returns (string, new_pos)."""
    length = struct.unpack_from("!H", buf, pos)[0]
    return buf[pos + 2: pos + 2 + length].decode(), pos + 2 + length


# ── Broker ────────────────────────────────────────────────────────────────────

#  Topic ACL: every topic a client may touch must fall under this prefix,
#  and only identities with can_command=True may PUBLISH to a topic
#  ending in COMMAND_SUFFIX (e.g. plant/small_scope/output/command).
#  Override via env for other deployments; defaults match this repo's
#  only known topics (see edge/small_scope/config.js).
TOPIC_PREFIX    = os.environ.get("MQTT_TOPIC_PREFIX", "plant/")
COMMAND_SUFFIX  = os.environ.get("MQTT_COMMAND_SUFFIX", "/command")


class MqttBroker:
    def __init__(self):
        # topic -> set of StreamWriter
        self._subs: dict[str, set] = defaultdict(set)
        # writer -> identity dict ({"email", "can_command"}) set on CONNECT
        self._identities: dict = {}
        # called with (topic: str, payload: bytes) on every inbound PUBLISH
        self.on_message = None
        # called with (username: str, password: str) -> dict | None on
        # CONNECT. Returns an identity dict on success, None to reject.
        # None callback = allow all (identity defaults to can_command=True).
        self.auth_callback = None

    # ── Internal publish (to all subscribers) ─────────────────────────────────

    async def _forward(self, topic: str, payload: bytes, exclude=None):
        topic_b = topic.encode()
        body    = struct.pack("!H", len(topic_b)) + topic_b + payload
        packet  = bytes([0x30]) + _encode_varlen(len(body)) + body
        dead    = set()
        for w in list(self._subs.get(topic, [])):
            if w is exclude or w.is_closing():
                dead.add(w)
                continue
            try:
                w.write(packet)
                await w.drain()
            except Exception:
                dead.add(w)
        for w in dead:
            self._subs[topic].discard(w)

    # ── Public publish (called by application code) ────────────────────────────

    async def publish(self, topic: str, payload):
        if isinstance(payload, str):
            payload = payload.encode()
        await self._forward(topic, payload)

    # ── Topic ACL ───────────────────────────────────────────────────────────────

    @staticmethod
    def _publish_allowed(topic: str, identity: dict) -> bool:
        if not topic.startswith(TOPIC_PREFIX):
            return False
        if topic.endswith(COMMAND_SUFFIX):
            return bool(identity.get("can_command"))
        return True

    # ── Per-client handler ─────────────────────────────────────────────────────

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        my_topics: set[str] = set()
        try:
            while True:
                hdr  = (await reader.readexactly(1))[0]
                ptype = (hdr >> 4) & 0x0F
                flags = hdr & 0x0F
                rem   = await _read_varlen(reader)
                body  = await reader.readexactly(rem) if rem else b""

                if ptype == CONNECT:
                    # Parse connect flags + credentials
                    # Variable header: proto_name(6 bytes)+proto_level(1)+connect_flags(1)+keepalive(2)=10
                    # body[0:2]=name_len, body[2:6]="MQTT", body[6]=level, body[7]=flags, body[8:10]=keepalive
                    connect_flags = body[7]
                    has_user = bool(connect_flags & 0x80)
                    has_pass = bool(connect_flags & 0x40)
                    has_will = bool(connect_flags & 0x04)
                    pos = 10
                    cid_len = struct.unpack_from("!H", body, pos)[0]; pos += 2 + cid_len
                    if has_will:
                        wt = struct.unpack_from("!H", body, pos)[0]; pos += 2 + wt
                        wm = struct.unpack_from("!H", body, pos)[0]; pos += 2 + wm
                    username = password = None
                    if has_user and pos < len(body):
                        l = struct.unpack_from("!H", body, pos)[0]; pos += 2
                        username = body[pos:pos+l].decode(); pos += l
                    if has_pass and pos < len(body):
                        l = struct.unpack_from("!H", body, pos)[0]; pos += 2
                        password = body[pos:pos+l].decode(errors="replace"); pos += l
                    rc = 0x00
                    identity = {"email": username or "", "can_command": True}
                    if self.auth_callback:
                        # auth_callback does blocking DB I/O — run off the
                        # event loop so one slow CONNECT can't stall every
                        # other client's PUBLISH/PINGREQ handling.
                        result = await asyncio.to_thread(self.auth_callback, username or "", password or "")
                        if result is None:
                            rc = 0x04  # bad credentials
                        else:
                            identity = result
                    writer.write(bytes([0x20, 0x02, 0x00, rc]))
                    await writer.drain()
                    if rc != 0:
                        return
                    self._identities[writer] = identity

                elif ptype == PUBLISH:
                    topic, pos = _read_str(body, 0)
                    qos = (flags >> 1) & 0x03
                    if qos:
                        pid = struct.unpack_from("!H", body, pos)[0]
                        pos += 2
                        writer.write(bytes([0x40, 0x02]) + struct.pack("!H", pid))  # PUBACK
                        await writer.drain()
                    msg = body[pos:]
                    identity = self._identities.get(writer, {})
                    if self._publish_allowed(topic, identity):
                        await self._forward(topic, msg, exclude=writer)
                        if self.on_message:
                            asyncio.create_task(self.on_message(topic, msg))
                    else:
                        print(f"[ACL] denied PUBLISH {topic!r} from {identity.get('email')!r}")

                elif ptype == SUBSCRIBE:
                    pid = struct.unpack_from("!H", body, 0)[0]
                    identity = self._identities.get(writer, {})
                    pos, granted = 2, []
                    while pos < len(body):
                        t, pos  = _read_str(body, pos)
                        qos_req = body[pos]; pos += 1
                        if t.startswith(TOPIC_PREFIX):
                            self._subs[t].add(writer)
                            my_topics.add(t)
                            granted.append(min(qos_req, 1))
                        else:
                            print(f"[ACL] denied SUBSCRIBE {t!r} from {identity.get('email')!r}")
                            granted.append(0x80)  # failure (outside allowed topic namespace)
                    suback = bytes([0x90]) + _encode_varlen(2 + len(granted))
                    writer.write(suback + struct.pack("!H", pid) + bytes(granted))
                    await writer.drain()

                elif ptype == PINGREQ:
                    writer.write(bytes([0xD0, 0x00]))
                    await writer.drain()

                elif ptype == DISCONNECT:
                    break

        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            pass
        finally:
            for t in my_topics:
                self._subs[t].discard(writer)
            self._identities.pop(writer, None)
            try:
                writer.close()
            except Exception:
                pass

    # ── Start TCP server ───────────────────────────────────────────────────────

    async def start(self, host: str = "0.0.0.0", port: int = 1883):
        ssl_context = build_ssl_context()
        server = await asyncio.start_server(self._handle, host, port, ssl=ssl_context)
        addr   = server.sockets[0].getsockname()
        scheme = "mqtts" if ssl_context else "mqtt"
        print(f"[MQTT] broker listening on {scheme}://{addr[0]}:{addr[1]}")
        return server


# ── TLS ───────────────────────────────────────────────────────────────────────

def build_ssl_context() -> "ssl.SSLContext | None":
    """Build the broker's TLS context from MQTT_TLS_CERT/MQTT_TLS_KEY env vars
    (paths to a PEM cert chain and private key). Returns None (plaintext) if
    either is unset, so local/dev runs without certs keep working."""
    cert_path = os.environ.get("MQTT_TLS_CERT")
    key_path  = os.environ.get("MQTT_TLS_KEY")
    if not cert_path or not key_path:
        print("[MQTT] MQTT_TLS_CERT/MQTT_TLS_KEY not set — broker running without TLS")
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    return context


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import signal

    async def _main():
        broker = MqttBroker()

        def _on_msg(topic, payload):
            print(f"[MQTT] {topic}: {payload.decode(errors='replace')}")

        broker.on_message = _on_msg
        server = await broker.start()
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, server.close)
        async with server:
            await server.serve_forever()

    asyncio.run(_main())
