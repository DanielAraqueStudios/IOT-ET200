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
  JWT auth in `auth.py`, plus one write endpoint:
  `POST /api/admin/devices` (also JWT-protected), which issues MQTT
  device tokens — see "Device token issuance" below. This is the one
  intentional exception to "no write endpoints" in this folder: it
  writes into `cloud/broker`'s database, not `plc_state`, and doesn't
  touch the PLC/gateway data path at all.
- `frontend/` — minimal Angular app that polls `GET /api/state` and
  renders current tag values, plus an admin form
  (`admin-device.component.ts`) to issue a device token. No write
  endpoints affecting PLC/gateway data exist anywhere in this repo.

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
# matches cloud/broker's check_device_token(email, token), sent as
# the MQTT CONNECT username/password fields. Issue one via this same
# backend's POST /api/admin/devices (see "Device token issuance"
# below) rather than inserting a row by hand:
export MQTT_USERNAME="your-account-email@example.com"
export MQTT_DEVICE_TOKEN="issued-by-POST-/api/admin/devices"
# Second DB connection, used ONLY by POST /api/admin/devices — must
# point at cloud/broker's own dedicated Postgres, not the one above:
export BROKER_DATABASE_URL="postgresql://broker:broker@localhost:5432/broker"
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

## Device token issuance

`POST /api/admin/devices` (admin-JWT-protected, same auth as the rest
of this API) is how a device — the `edge/small_scope` gateway, or any
other MQTT client — gets credentials to authenticate to `cloud/broker`.
It writes into **the broker's own dedicated Postgres**, not this
backend's `DATABASE_URL`, over a second connection string,
`BROKER_DATABASE_URL` (see `backend/env.example`). The `User` table
shape it writes to is defined once, in `cloud/broker/prisma/schema.prisma`
— `backend/broker_db.py` mirrors that schema by hand and must be kept
in sync with it if it ever changes; this backend never manages
migrations for that table (`cloud/broker`'s Prisma migrations do).

```bash
curl -X POST http://localhost:8000/api/admin/devices \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "iot2050-gateway@example.com", "can_command": false}'
# -> {"email": "iot2050-gateway@example.com", "device_token": "...", "can_command": false}
```

The token is generated with `secrets.token_urlsafe(32)` (not a
predictable value), **hashed with bcrypt before being stored** (only
the hash goes into the broker's `User.deviceToken` — see
`cloud/broker/README.md` "Auth model"), and is **returned exactly
once**, in that API response — there is no way to retrieve it again
afterward; even this backend only ever holds the plaintext token for
the duration of this one request. Copy it immediately into
`edge/small_scope/config.js`'s `mqtt.deviceToken` (or wherever else
that device's MQTT client reads its credentials from). Calling the
endpoint again for the same email re-issues (overwrites) that
device's token — the old one stops working immediately.

`can_command` controls the broker's topic ACL (see
`cloud/broker/README.md` "Topic ACL"): only set it `true` for a
device/client that legitimately needs to PUBLISH to a `/command`
topic — not just subscribe to one, and not for telemetry-only
publishers like the gateway's status topics. It defaults to `false`
if omitted.

The frontend's admin form (`admin-device.component.ts`, shown below
the tag table once logged in) does the same thing — with a checkbox
for `can_command` and a copy button — for anyone who'd rather not use
`curl`.

**Not built** (flagged as out of scope for this task, not solved
here): revoking a token without issuing a new one, listing existing
devices, or any UI/endpoint to see which devices currently hold a
token.

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
  — username is the account email, password is the device token
  returned by this backend's own `POST /api/admin/devices` (see
  "Device token issuance" above).
- `BROKER_DATABASE_URL` — a second, separate Postgres connection
  string (the broker's dedicated DB, not this service's own
  `DATABASE_URL`), used only by `POST /api/admin/devices`.
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

This folder's `railway.toml` declares two services — `dashboard-backend`
and `dashboard-frontend` — built from their respective Dockerfiles.
Postgres is provisioned separately as a Railway-managed plugin, not
declared in `railway.toml`. `cloud/broker` (this repo's MQTT broker,
see its own README) belongs in the **same Railway project** as these
two services, since it shares project-level variables with
`dashboard-backend` — see step 4 below. Follow these steps from
scratch:

1. **Create the project.** In the Railway dashboard, click **New
   Project** → **Empty Project** (or `railway init` from this repo's
   root if using the CLI). This project will hold `dashboard-backend`,
   `dashboard-frontend`, this service's Postgres plugin, and
   `cloud/broker` (with its own, separate Postgres plugin) as sibling
   services, so they can share project-level variables.

2. **Add the backend service.**
   - **New Service** → **GitHub Repo**, pick this repo.
   - Set the service's **Root Directory** to `cloud/dashboard/backend`
     (Settings → Source) — type it or pick `backend` from the folder
     picker. Then, in the same Settings page under **Build**, set
     **Dockerfile Path** to just `Dockerfile` (no subfolder prefix —
     it's already resolved relative to Root Directory). Putting the
     subfolder in *both* fields, e.g. Root Directory
     `/cloud/dashboard/backend` **and** Dockerfile Path
     `/cloud/dashboard/backend/Dockerfile`, breaks the build: Railway
     can't find `requirements.txt` because the build context no longer
     matches where the Dockerfile's `COPY` instructions expect it
     (`failed to compute cache key ... "/requirements.txt": not
     found`). Rename the service to `dashboard-backend` to match
     `railway.toml`.
   - Railway injects `$PORT` automatically; `uvicorn` in
     `backend/Dockerfile` must bind to it (already configured).

3. **Provision Postgres.** In the same project, **New** → **Database**
   → **Add PostgreSQL**. Railway creates the plugin and exposes a
   `DATABASE_URL` reference variable. On the `dashboard-backend`
   service's **Variables** tab, add `DATABASE_URL` and reference the
   Postgres plugin's value (Railway's variable picker offers this —
   don't hand-copy the connection string). **Do this before the first
   deploy, not after** — `backend/models.py` reads `DATABASE_URL` at
   import time with no fallback, so a deploy without it crashes
   immediately on startup with `KeyError: 'DATABASE_URL'` (visible in
   `railway logs`), even though the build itself succeeded. Run
   `db/schema.sql` against that database once (e.g. `railway connect
   postgres` then `\i db/schema.sql`, or `psql "$DATABASE_URL" -f
   db/schema.sql` with the URL from the plugin's **Connect** tab). This
   Postgres is **dedicated to the dashboard** — `cloud/broker`
   provisions and uses its own, separate Postgres plugin;
   `DATABASE_URL` is never a shared variable.

4. **Set the backend's variables — Shared Variables for anything
   broker-related, per-service for the rest.** Deploy `cloud/broker`
   into this same project first (see its README's "Deploying to
   Railway" section), then come back here:
   - In the Railway dashboard, open the **project** (not a service) →
     **Settings → Shared Variables**, and define:
     - `MQTT_URL` — the broker's reachable `mqtts://host:port`, which
       you only get after the broker's Railway **TCP Proxy** is
       provisioned (see its README). Set it here once.
     - A shared cert variable (e.g. `MQTT_TLS_CERT_PEM`) holding the
       broker's self-signed certificate content — the **same cert**
       the broker loads as `MQTT_TLS_CERT`. Shared Variables share one
       underlying value across services; each service still maps it
       to its own locally-expected variable name.
   - On `dashboard-backend` → **Variables**, enable/reference those two
     shared variables so they populate this service's `MQTT_URL` and
     `MQTT_TLS_CA_CERT` respectively (Railway's variable picker lets you
     pick "from Shared Variables" and map it to a service-local name —
     use `${{shared.MQTT_TLS_CERT_PEM}}` style references, or the
     dashboard's point-and-click equivalent). `MQTT_TLS_CA_CERT` needs
     this cert content reachable at a path inside the container — the
     simplest interim option is a Railway **volume** mounted into the
     backend service with the cert content written to it from the
     shared variable at startup, since this repo doesn't yet decide a
     permanent distribution mechanism (see "Not yet decided" below).
   - Still per-service on `dashboard-backend` (not shared — these are
     either per-client credentials or backend-only config): set
     `MQTT_OUTPUT_TOPIC`, `MQTT_INPUT_TOPIC`, `MQTT_USERNAME`,
     `MQTT_DEVICE_TOKEN`, `JWT_SECRET`, `DASHBOARD_ADMIN_USER`,
     `DASHBOARD_ADMIN_PASSWORD_HASH`. See the "Env vars needed" section
     above for what each one means.
   - **`BROKER_DATABASE_URL`** (per-service, NOT a Shared Variable —
     see `cloud/broker/README.md`'s Shared Variables section for why):
     on `dashboard-backend` → **Variables**, reference `cloud/broker`'s
     Postgres plugin directly (Railway's variable picker can reach
     across services in the same project) rather than hand-copying its
     connection string.
   - **Issuing the first device token:** the broker's `User` table
     starts empty — `MQTT_USERNAME`/`MQTT_DEVICE_TOKEN` here won't
     authenticate until you call this backend's own
     `POST /api/admin/devices` once (see "Device token issuance"
     above) and set these two vars to what it returns. Do this after
     step 5 deploys the backend, then redeploy (or just set the vars
     and let Railway restart the service) so `mqtt_ingest` picks them
     up.

5. **Deploy the backend** — pushing to the linked branch (or `railway
   up` with this folder as cwd) triggers a build from
   `backend/Dockerfile`. Watch the deploy logs; once healthy, open
   **Settings → Networking** and generate a public domain (or add a
   custom domain) for `dashboard-backend` so the frontend and anyone
   testing the API can reach it.

6. **Add the frontend service.** Same as step 2 but **Dockerfile
   Path** = `frontend/Dockerfile`, service name `dashboard-frontend`.
   Before the first build, set `apiUrl` in `frontend/src/environment.ts`
   to the backend domain from step 5 (Angular reads this at build time,
   not from a runtime env var — see `frontend/env.example`) and commit
   that change so the Dockerfile picks it up. The frontend's
   `nginx.conf.template` serves the built app on Railway's injected
   `$PORT`; no extra variables are required for this service.

7. **Deploy the frontend** the same way as step 5, then generate its
   own public domain from **Settings → Networking**. That's the URL
   users open.

8. **Verify it's live.** Hit the backend's domain directly:
   `POST /auth/login` with the admin credentials from step 4, then
   `GET /api/state` with the returned bearer token (see "Getting a
   token / calling the API" above). Also try `POST /api/admin/devices`
   (see "Device token issuance") to confirm `BROKER_DATABASE_URL` is
   wired correctly. Then open the frontend's domain in a browser and
   confirm it renders tag values without errors in the console/network
   tab, and that the device-token form works.

**MQTT broker reachability:** this backend only connects *out* to
`cloud/broker` (this repo's own MQTT broker service, deployed as a
sibling service in the same Railway project — see its README) via
`MQTT_URL`. That broker's `MQTT_PORT` listens on a different port from
its own HTTP API's `$PORT` and needs its own Railway **TCP Proxy**
(configured on the broker service, not this one) to be reachable at
all over `mqtts://` — confirm that's provisioned before assuming
`MQTT_URL` will connect (same caveat documented in
`../../edge/small_scope/README.md`'s "MQTT broker" section).

Both Dockerfiles are written for this POC stage — review resource
limits/health checks before relying on this for anything beyond a
demo.

## Not yet decided / needs confirmation

- Hosting target for backend + Postgres + frontend (not assumed here).
- Where `MQTT_TLS_CA_CERT` gets fetched from / how it's distributed to
  deployments (not just local dev) — not decided yet.
