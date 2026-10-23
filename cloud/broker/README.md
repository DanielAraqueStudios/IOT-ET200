# MQTT Broker

Minimal async MQTT broker (handles CONNECT, PUBLISH QoS 0/1, SUBSCRIBE,
PINGREQ, DISCONNECT — no persistence, no retained messages). Brought
into this repo from the separate `Paint-mixer` project, where it was
originally embedded inside that app's FastAPI service; here it's its
own standalone deployable service.

## How it fits into this repo

- `edge/small_scope` (the IOT2050 gateway, never deployed to Railway)
  publishes PLC tag state to this broker and subscribes to it for any
  inbound commands, over `mqtts://`.
- `cloud/dashboard/backend` only connects **out** to this broker via
  `MQTT_URL` (see `mqtt_ingest.py`) — it does not host or proxy the
  broker itself. This service is what makes that `MQTT_URL` resolve to
  something real when deployed.

Neither of those two services is modified by bringing the broker in
here — this folder is purely the third piece they both talk to.

## TLS model

`broker.py`'s `build_ssl_context()` reads `MQTT_TLS_CERT` /
`MQTT_TLS_KEY` (PEM cert chain + private key paths) and serves
`mqtts://` when both are set, falling back to plaintext `mqtt://` if
either is unset (local/dev only).

The certificate is **self-signed and trusted manually by clients**,
not CA-issued — this was an explicit decision and is not changed here.
Clients (the edge gateway, the dashboard backend) must be given a copy
of this exact cert and pin it (e.g. `MQTT_TLS_CA_CERT` on the dashboard
side) rather than relying on the public CA trust store, which a
self-signed cert will always fail against.

## Auth model

`auth.py`'s `check_device_token(email, token)` validates the MQTT
CONNECT username/password fields against a `User.deviceToken` row,
wired in as the broker's `auth_callback` (see `main.py`). This is kept
**in addition to TLS, not instead of it** — defense in depth: TLS
secures the transport, the device token authorizes the specific
client. Do not remove or weaken this check.

`models.py` here only declares the columns of `User` that
`check_device_token` reads (`id`, `email`, `passwordHash`,
`deviceToken`, `createdAt`) — it must point at the same Postgres table
that actually issues/stores device tokens. **Not yet wired up in this
repo**: there is no user-registration/device-token-issuing endpoint
here (the original one lived in Paint-mixer's own `auth.py`, which was
intentionally left out since it's app-specific, not broker
infrastructure). `DATABASE_URL` needs to point at whichever Postgres
ends up owning that table — confirm before deploying for real traffic.

## Running locally

```bash
cd cloud/broker
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:pass@localhost:5432/plc"
export MQTT_PORT=1883
uvicorn main:app --reload --port 8000
```

`GET http://localhost:8000/health` reports broker status. The actual
MQTT listener is on `MQTT_PORT` (plaintext if `MQTT_TLS_CERT`/
`MQTT_TLS_KEY` are unset).

## Deploying to Railway

Declared in `railway.toml` at this folder's root, built from
`Dockerfile`. Two distinct ports are involved:

- **`$PORT`** (Railway-injected, HTTP) — serves only `GET /health`,
  used for Railway's deploy health check. Not the MQTT port.
- **`MQTT_PORT`** (set via env var, default `1883`) — the actual MQTT
  listener. Railway's HTTP `$PORT`/public domain do **not** expose
  raw TCP, so this port needs its own **Railway TCP Proxy**: from the
  Railway dashboard, open this service's Settings → Networking → TCP
  Proxy, and point it at `MQTT_PORT`. Railway then hands back a proxy
  `host:port` pair — that's the address clients (`MQTT_URL` on the
  dashboard side, the edge gateway) actually connect to, not
  `$PORT`/the public HTTP domain.

Required env vars (see `env.example`):

- `DATABASE_URL` — Postgres holding the `User.deviceToken` table (see
  Auth model above — not yet decided which instance this should be).
- `MQTT_PORT` — port the MQTT listener binds to internally.
- `MQTT_TLS_CERT` / `MQTT_TLS_KEY` — self-signed cert + key for
  `mqtts://`. Once deployed, fetch this cert (or its fingerprint) so
  it can be pinned on the client side (`MQTT_TLS_CA_CERT` for the
  dashboard backend) — do not fabricate or assume a value.

This Dockerfile/service is written for POC stage — review resource
limits/health checks before relying on this for anything beyond a demo.
