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
`deviceToken`, `createdAt`).

**Database: dedicated, not shared.** This service gets its own
Postgres (a separate Railway Postgres plugin), not Paint-mixer's DB —
it only ever needs this one trimmed table.

**Known gap / TODO — device tokens are not populated yet.** There is
no user-registration/device-token-issuing endpoint in this service
(the original one lived in Paint-mixer's own `auth.py`, intentionally
left out here since it's app-specific, not broker infrastructure). So
right after this dedicated DB is created, its `User` table is empty —
`check_device_token` will reject everything until rows exist. Until a
real issuance flow is built somewhere, rows must be inserted manually
(e.g. a one-off `INSERT INTO "User" (email, "passwordHash",
"deviceToken") VALUES (...)` or a short script) for each client that
needs to connect. This is flagged as a gap, not solved here — building
token issuance is new scope beyond bringing the broker in and
deploying it.

## Database migrations

Schema/migrations for this dedicated Postgres are managed with
**Prisma** (`prisma/schema.prisma`), even though the running service
is Python/FastAPI. Prisma is used **only as the migration tool here —
not as the runtime client**: the actual `check_device_token` query at
runtime still goes through SQLAlchemy (`models.py`, `auth.py`). This
means `prisma/schema.prisma` and `models.py` describe the same table
by hand and must be kept in sync manually when either changes.

- `prisma/schema.prisma` — the `User` model, matching `models.py`.
- `prisma/migrations/` — one folder per migration (the committed
  `20261023024200_init` creates the `User` table). Add a new migration
  with `npx prisma migrate dev --name <description>` against a local/
  dev `DATABASE_URL` (requires Node + `npm install` once, see
  `package.json`), then commit the generated `prisma/migrations/<ts>_<name>/migration.sql`.
- **Deploy-time**: the `Dockerfile`'s `CMD` runs `npx prisma migrate
  deploy` before starting `uvicorn`, applying any pending migrations
  against `DATABASE_URL` on every deploy — this is Prisma's documented
  pattern for non-interactive/production migrations (as opposed to
  `prisma migrate dev`, which is dev-only and asks for confirmation).
  The `Dockerfile` installs Node.js solely to run this CLI step.

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

- `DATABASE_URL` — this service's own dedicated Postgres plugin
  (see "Database: dedicated, not shared" above). Service-specific,
  not a Railway Shared Variable.
- `MQTT_PORT` — port the MQTT listener binds to internally.
- `MQTT_TLS_CERT` / `MQTT_TLS_KEY` — self-signed cert + key for
  `mqtts://`. Once deployed, fetch this cert (or its fingerprint) so
  it can be pinned on the client side (`MQTT_TLS_CA_CERT` for the
  dashboard backend) — do not fabricate or assume a value.

### Railway Shared Variables

Anything this service and `cloud/dashboard` both need should be set
once as a project-level **Shared Variable** in Railway rather than
duplicated into each service's own env vars:

- **The broker's public TLS certificate** — the broker loads it as
  `MQTT_TLS_CERT` (cert half only; the private key `MQTT_TLS_KEY`
  stays broker-only and must *not* be a shared variable), and the
  dashboard backend trusts that exact same cert as
  `MQTT_TLS_CA_CERT`. Same file/content, different variable name per
  service — document that mapping wherever the shared variable is
  defined, don't assume the names line up automatically.
- **The broker's reachable address** (host + TCP Proxy port), once
  known after deploy — consumed as `MQTT_URL` by the dashboard
  backend.

Per-service, NOT shared: each service's `DATABASE_URL` (separate,
dedicated Postgres instances), `MQTT_TLS_KEY` (broker's private key),
and any individual device token / `MQTT_USERNAME` /
`MQTT_DEVICE_TOKEN` a specific client uses to authenticate — those are
per-client credentials, not architecture-level config, and don't
belong in a project-wide shared variable.

This Dockerfile/service is written for POC stage — review resource
limits/health checks before relying on this for anything beyond a demo.
