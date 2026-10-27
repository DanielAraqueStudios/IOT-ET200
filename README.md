# IOT-ET200

PLC-to-cloud IIoT integration: a Siemens S7-1500 PLC exposes selected
tags over OPC UA to a gateway running on a SIMATIC IOT2050, which
bridges them to an MQTT broker consumed by a cloud dashboard deployed
on Railway.

Full architecture and design rationale: [`Arquitecture.md`](./Arquitecture.md).

## Repository layout

```
edge/
  small_scope/        OPC UA <-> MQTT gateway — runs on the IOT2050
cloud/
  dashboard/           FastAPI backend + Angular frontend — deploys to Railway
Arquitecture.md         Network architecture and design decisions
```

### `edge/small_scope/`

Minimal OPC UA to MQTT gateway. Reads/writes PLC tags over OPC UA and
publishes/subscribes to MQTT topics on the Railway-hosted broker. Runs
as a systemd service **on the IOT2050 itself** — it needs direct
network access to the PLC's OPC UA server on the plant-local network,
so it is never deployed to Railway or any other cloud host.

See [`edge/small_scope/README.md`](./edge/small_scope/README.md) for
setup, behavior, and environment variables, and
[`edge/small_scope/TIA_PORTAL_BUILD_GUIDE.md`](./edge/small_scope/TIA_PORTAL_BUILD_GUIDE.md)
for the TIA Portal V18 steps required on the PLC side.

### `cloud/dashboard/`

Read-only operations dashboard: a FastAPI backend ingests MQTT
telemetry into Postgres and exposes a small REST API (JWT-protected),
and an Angular frontend displays current and historical PLC
input/output state. No control or write-back capability — display
only. Deploys to Railway.

See [`cloud/dashboard/README.md`](./cloud/dashboard/README.md) for
local setup, environment variables, and Railway deployment steps.

## Data flow

```
PLC (S7-1500, OPC UA server)
   |  OPC UA, plant-local network only
   v
edge/small_scope  (IOT2050 gateway)
   |  MQTT over TLS + device-token auth
   v
MQTT broker  (Railway)
   |
   v
cloud/dashboard  (Railway: FastAPI + Postgres + Angular)
```

## Deploying to Railway

`cloud/broker` and `cloud/dashboard` (`backend` + `frontend`) deploy as
three separate services inside **one Railway project**, because the
backend and broker must share a couple of values via Railway's
project-level **Shared Variables**. Full detail lives in
[`cloud/broker/README.md`](./cloud/broker/README.md) ("Deploying to
Railway" / "Railway Shared Variables") and
[`cloud/dashboard/README.md`](./cloud/dashboard/README.md) ("Deploying
to Railway") — this is the condensed order to follow so you don't have
to reconstruct it from two files:

1. **Create (or open) one Railway project.** Everything below goes
   into this same project, not separate ones.

2. **Deploy `cloud/broker` first.**
   - New Service → GitHub Repo → this repo.
   - Settings → Source: **Root Directory** = `cloud/broker`.
   - Settings → Build: **Dockerfile Path** = `Dockerfile` (just
     `Dockerfile`, not `cloud/broker/Dockerfile` — Root Directory
     already scopes it; combining both breaks the build context).
   - Add a Postgres plugin to this service only (its own
     `DATABASE_URL` — never shared with the dashboard).
   - Set this service's own vars: `MQTT_PORT` (e.g. `1883`),
     `HTTP_PORT` (e.g. `8080` — **do not** leave uvicorn bound to
     Railway's `$PORT`; on this service `$PORT` tracks the TCP Proxy's
     port below, not the HTTP domain's, so uvicorn and the MQTT
     listener would try to bind the same port in the same process and
     crash-loop — see `cloud/broker/README.md` "Two distinct ports"),
     `MQTT_TLS_CERT`, `MQTT_TLS_KEY`. Generate the self-signed cert/key
     locally first with `scripts/generate_broker_cert.py` (pure
     Python, works on Windows without `openssl`) — use the TCP Proxy
     hostname from the step below as the CN/SAN once you have it (a
     cert minted before that exists can be regenerated after):
     ```bash
     python scripts/generate_broker_cert.py --host <tcp-proxy-host>
     ```
     It prints both files' full PEM content at the end — paste
     `broker.crt`'s **exact full content, including the `BEGIN`/`END`
     lines**, into `MQTT_TLS_CERT`, and `broker.key`'s into
     `MQTT_TLS_KEY`. A partial/wrong paste here is the single most
     common cause of a broker that crashes on boot with
     `ssl.SSLError: [X509: KEY_VALUES_MISMATCH]` — verify a pasted pair
     actually matches by comparing MD5 of each file's modulus
     (`openssl x509 -noout -modulus -in broker.crt | openssl md5` must
     equal `openssl rsa -noout -modulus -in broker.key | openssl md5`).
   - Deploy. Confirm `GET /health` on `HTTP_PORT`'s public domain
     goes healthy (this is Railway's own deploy health check, separate
     from the MQTT port — and separate from `$PORT`, see above).
   - Settings → Networking → **TCP Proxy**, point it at `MQTT_PORT`.
     Railway returns a public `host:port` — this only exists after the
     service is deployed, it's not something you can set up front.

3. **Publish the project-level Shared Variables** — project
   **Settings → Shared Variables** (the project's own settings, not a
   service's Variables tab):
   - `MQTT_URL` = `mqtts://<tcp-proxy-host>:<tcp-proxy-port>` from
     step 2's TCP Proxy.
   - `MQTT_TLS_CERT_PEM` = the exact same cert content as the broker's
     own `MQTT_TLS_CERT` from step 2.

4. **Deploy `cloud/dashboard/backend`** into the same project.
   - Root Directory = `cloud/dashboard/backend`, same Dockerfile-path
     rule as step 2.
   - On this service's own **Variables** tab, reference the two Shared
     Variables from step 3 and map them to the names this service
     expects: Shared `MQTT_URL` → local `MQTT_URL`; Shared
     `MQTT_TLS_CERT_PEM` → local `MQTT_TLS_CA_CERT`.
   - Add a **separate** Postgres plugin dedicated to this service —
     its `DATABASE_URL` is never shared with the broker's.
   - Set `BROKER_DATABASE_URL` by referencing the **broker's** Postgres
     plugin directly from this service's Variables tab (Railway's
     picker can reach across services in the same project). This is
     deliberately *not* a Shared Variable — see
     `cloud/broker/README.md`'s Shared Variables section for why.
   - Set the remaining per-service vars: `JWT_SECRET`,
     `DASHBOARD_ADMIN_USER`, `DASHBOARD_ADMIN_PASSWORD_HASH`,
     `MQTT_INPUT_TOPIC`, `MQTT_OUTPUT_TOPIC`. Generate the first two
     values locally:
     ```bash
     # JWT_SECRET
     openssl rand -hex 32

     # DASHBOARD_ADMIN_PASSWORD_HASH — bcrypt hash of your chosen
     # admin password (pip install "passlib[bcrypt]" first); the
     # plaintext password itself never goes into Railway
     python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-chosen-password'))"
     ```
   - Deploy, confirm healthy.

5. **Issue the first device token** — call `POST
   /api/admin/devices` on the now-deployed backend (see
   `cloud/dashboard/README.md`, "Device token issuance"). Take the
   `device_token` it returns and set `MQTT_USERNAME` /
   `MQTT_DEVICE_TOKEN` on `dashboard-backend`, then redeploy (or let
   Railway auto-restart on the var change) so `mqtt_ingest` picks them
   up. Nothing can authenticate to the broker before this step — the
   `User` table starts empty.

6. **Deploy `cloud/dashboard/frontend`** the same way (its own section
   in `cloud/dashboard/README.md`).

**Quick reference — what's shared vs. per-service:**

| Shared (project-level) | Per-service |
|---|---|
| `MQTT_URL` | `DATABASE_URL` (each service has its own) |
| `MQTT_TLS_CERT_PEM` (→ `MQTT_TLS_CERT` on broker, `MQTT_TLS_CA_CERT` on backend) | `MQTT_TLS_KEY` (broker's private key — never shared) |
| | `HTTP_PORT` (broker only — fixed, *not* Railway's `$PORT`; see `cloud/broker/README.md` "Two distinct ports") |
| | `BROKER_DATABASE_URL` (backend → broker's Postgres, cross-service reference, not Shared Variables) |
| | `MQTT_USERNAME` / `MQTT_DEVICE_TOKEN` (per-client credentials) |
| | `JWT_SECRET`, `DASHBOARD_ADMIN_USER`, `DASHBOARD_ADMIN_PASSWORD_HASH` |

## Security posture

- The PLC never connects directly to the internet; only the IOT2050
  gateway has outbound WAN access.
- The MQTT broker connection uses TLS with a pinned self-signed
  certificate, plus device-token authentication (defense in depth —
  TLS does not replace the token check).
- The dashboard's REST API is protected separately by JWT, independent
  of the MQTT broker's own auth.
- No remote command path has a PLC-side interlock against local
  control in this minimal scope — see `Arquitecture.md` and
  `edge/small_scope/README.md` for the accepted-risk rationale before
  extending this beyond a lab/POC deployment.

## Future implementation

Not built yet — ideas evaluated and intentionally deferred, not forgotten:

- **TOTP two-factor login** (Google Authenticator–style): per-account
  secret, QR-code enrollment, a 6-digit code required at login in
  addition to the password. Moderate effort on its own (`pyotp` handles
  the actual TOTP logic), but the dashboard currently has a single
  hardcoded admin account via `DASHBOARD_ADMIN_USER`/
  `DASHBOARD_ADMIN_PASSWORD_HASH` env vars, not a real accounts table —
  "per account" 2FA implies building that table first.
- **Step-up re-authentication before sending a PLC command**: require a
  fresh TOTP code again specifically at the point of calling
  `POST /api/command` (see "Deploying to Railway" above), not just at
  login. This is the harder half: a TOTP code is valid for its full
  ~30s window and reusable within it, so a naive re-check allows replay
  within that window; doing this properly means deciding between
  re-entering a code on every single command (safer, worse UX) or a
  short-lived "step-up" approval covering a burst of commands (better
  UX, more to build — it's effectively a second, shorter-lived session
  layered on top of the JWT), plus rate-limiting/lockout on failed
  codes, which doesn't exist anywhere in this app today and matters
  more here since this gate controls physical hardware.
