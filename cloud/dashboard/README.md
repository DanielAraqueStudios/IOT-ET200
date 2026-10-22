# PLC Cloud Dashboard

Read-only cloud dashboard for the `../../edge/small_scope` gateway.
Shows current and historical input/output tag state. **No
control/write-back UI, no HMI** — display only, by design. This is the
**cloud half** of this repo — the only part ever deployed to Railway
(see `../../edge/small_scope/README.md` for the half that isn't).

## Architecture

- `db/schema.sql` — single `plc_state` table (`id, tag_name, value,
  updated_at`); every MQTT message is inserted as a new row, so the
  "current" value per tag is just its latest row.
- `backend/` — FastAPI service. `mqtt_ingest.py` subscribes over MQTT
  TLS + device-token auth (`mqtts://`, matching the edge gateway's auth
  model) to `plant/small_scope/output/state` and
  `plant/small_scope/input/state`, and writes every message into
  `plc_state`. `main.py` exposes read-only REST endpoints
  (`GET /api/state`, `GET /api/history/{tag_name}`), protected by the
  JWT auth in `auth.py`.
- `frontend/` — minimal Angular app that polls `GET /api/state` and
  renders current tag values. No write endpoints exist anywhere in
  this repo.

## Running locally

### Database

```bash
createdb plc
psql plc -f db/schema.sql
```

### Backend

See `backend/env.example` for the full list with comments (copy it to
`.env` and fill it in, or export each var directly):

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL="postgresql://user:pass@localhost:5432/plc"
export MQTT_URL="mqtts://your-app.up.railway.app:1884"
# Broker auth: TLS + device token (defense in depth, not TLS-only) —
# matches the Paint-mixer broker's check_device_token(email, token),
# sent as the MQTT CONNECT username/password fields:
export MQTT_USERNAME="your-account-email@example.com"
export MQTT_DEVICE_TOKEN="$(get this from GET /api/auth/device-token)"
# Broker cert is self-signed (not CA-issued) — point this at a saved
# copy of that exact cert so paho trusts it specifically. Omitting it
# falls back to no cert validation at all (logged as a warning) —
# fine for a lab/POC, not for anything beyond that.
export MQTT_TLS_CA_CERT="/path/to/broker-self-signed-cert.pem"
# Optional overrides, default to the small_scope gateway's topics:
export MQTT_OUTPUT_TOPIC="plant/small_scope/output/state"
export MQTT_INPUT_TOPIC="plant/small_scope/input/state"
# REST API auth (does NOT affect the MQTT connection, which stays
# TLS-only / no-auth):
export JWT_SECRET="change-me-to-a-long-random-value"
export DASHBOARD_ADMIN_USER="admin"
# Generate with: python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-password'))"
export DASHBOARD_ADMIN_PASSWORD_HASH="$2b$12$..."
uvicorn main:app --reload
```

### Getting a token / calling the API

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/state
```

Tokens expire after 1 hour; just log in again to get a new one — there
is no refresh-token flow.

### Frontend

```bash
cd frontend
npm install
npm start
```

Set `apiUrl` in `src/environment.ts` to the backend's URL for non-local
deployments.

## Env vars needed (not guessed — confirm before deploying)

- `DATABASE_URL` — Postgres connection string.
- `MQTT_URL` — the broker's `mqtts://host:port`. Requires the
  Paint-mixer broker TLS fix (tracked in that repo) to actually be
  reachable over `mqtts://`.
- `MQTT_USERNAME` / `MQTT_DEVICE_TOKEN` — the broker still requires
  `check_device_token` auth (TLS is on top of this, not instead of it)
  — username is the account email, password is that account's device
  token from `GET /api/auth/device-token` in Paint-mixer.
- `MQTT_TLS_CA_CERT` — path to the broker's self-signed cert PEM, so
  the client trusts that specific cert instead of the public CA store
  (which a self-signed cert will always fail against). Omitting it
  disables cert validation entirely — logged as a warning, lab/POC
  only.
- `MQTT_OUTPUT_TOPIC` / `MQTT_INPUT_TOPIC` — override if the gateway's
  topic names change.
- `JWT_SECRET` — signing secret for the dashboard REST API's JWTs.
  Used only for the REST API; unrelated to the MQTT connection above.
- `DASHBOARD_ADMIN_USER` / `DASHBOARD_ADMIN_PASSWORD_HASH` — the
  single admin login accepted by `POST /auth/login` (bcrypt hash, not
  a plaintext password).

## Auth

The REST API (`/api/state`, `/api/history/{tag_name}`) requires a
`Authorization: Bearer <token>` header. Get a token from
`POST /auth/login` with the admin credentials above; it expires after
1 hour (no refresh tokens — just log in again). The MQTT ingest
connection is intentionally unauthenticated/TLS-only and is not
affected by any of this.

The Angular frontend stores the token in `sessionStorage` (cleared
when the tab closes) rather than `localStorage`, since a 1-hour bearer
token sitting in `localStorage` would otherwise persist indefinitely
if a user never explicitly logs out.

This is separate from the MQTT connection's auth: the broker requires
TLS *and* `check_device_token` (username = account email, password =
device token) — see the env vars above.

## Deploying to Railway

Two services, declared in `railway.toml` at this folder's root:

- **`dashboard-backend`** — built from `backend/Dockerfile` (binds to
  Railway's injected `$PORT`). Attach a Railway Postgres plugin to get
  `DATABASE_URL` automatically; set the rest of `backend/env.example`'s
  vars (renamed `.env.example` → service variables in the Railway
  dashboard) manually.
- **`dashboard-frontend`** — built from `frontend/Dockerfile`
  (multi-stage: `ng build` then served via nginx on `$PORT`). Before
  building, set `apiUrl` in `frontend/src/environment.ts` to the
  backend service's public Railway domain.

**MQTT broker reachability:** this backend only connects *out* to the
existing Paint-mixer-hosted broker (`MQTT_URL`) — there's no broker
service to deploy here. That broker's `MQTT_PORT` listens on a
different port from its own HTTP API's `$PORT` and needs its own
Railway **TCP Proxy** to be reachable at all (same caveat already
documented in `../../edge/small_scope/README.md`'s "MQTT broker"
section) — confirm that's configured on the Paint-mixer project before
assuming `MQTT_URL` will connect.

Both Dockerfiles are written for this POC stage — review resource
limits/health checks before relying on this for anything beyond a
demo.

## Not yet decided / needs confirmation

- Hosting target for backend + Postgres + frontend (not assumed here).
- Where `MQTT_TLS_CA_CERT` gets fetched from / how it's distributed to
  deployments (not just local dev) — not decided yet.
