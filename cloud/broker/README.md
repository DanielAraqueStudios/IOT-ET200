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
`MQTT_TLS_KEY` and serves `mqtts://` when both are set, falling back to
plaintext `mqtt://` if either is unset (local/dev only). Each value is
**either** a path to a PEM file (the local Docker stack mounts real
files) **or** the PEM content itself, detected by the `-----BEGIN`
prefix — a cloud host like Railway has no shared filesystem to point a
variable at, so there the Railway dashboard's variable value holds the
cert/key content directly, and `build_ssl_context()` writes it to a
throwaway file before `load_cert_chain()` (which only accepts a path).

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

`User.deviceToken` stores a **bcrypt hash** of the token, never the
plaintext value — `check_device_token` verifies with `passlib`, the
same pattern as `passwordHash`. A DB read/backup leak does not hand
out usable credentials directly. The issuance endpoint
(`cloud/dashboard/backend`'s `POST /api/admin/devices`) hashes before
writing; it never stores the plaintext token anywhere.

On success, `check_device_token` returns an **identity** —
`{"email", "can_command"}` — not just a bool. `broker.py` keeps this
per-connection and enforces a topic ACL from it (see "Topic ACL"
below).

`models.py` here only declares the columns of `User` that
`check_device_token` reads (`id`, `email`, `passwordHash`,
`deviceToken`, `canCommand`, `createdAt`).

**Database: dedicated, not shared.** This service gets its own
Postgres (a separate Railway Postgres plugin), not Paint-mixer's DB —
it only ever needs this one trimmed table.

## Topic ACL

Every PUBLISH/SUBSCRIBE must target a topic starting with
`MQTT_TOPIC_PREFIX` (default `plant/`, matching the only topics this
repo's edge gateway uses) — anything outside that namespace is
rejected (SUBSCRIBE gets a `0x80` failure code per-topic; PUBLISH is
silently dropped after PUBACK, since MQTT 3.1.1 has no reject code for
publishes).

On top of that, a topic ending in `MQTT_COMMAND_SUFFIX` (default
`/command` — i.e. anything that can write back to the PLC) additionally
requires the connecting identity's `canCommand=true`. Most devices
(e.g. the gateway, which only publishes telemetry and *subscribes* to
the command topic) don't need this; only a client that legitimately
needs to *send* commands should be issued a token with `can_command:
true` at issuance time (see `cloud/dashboard/README.md`).

This is still a flat ACL (one prefix, one permission flag) — it stops
an arbitrary authenticated client from commanding the PLC or snooping
unrelated topics, but it does not scope telemetry per-device. See
`Arquitecture.md` for the accepted-risk discussion of what's still not
covered (PLC-side interlock between remote and local control).

## Device token issuance

This service has no registration/issuance endpoint of its own by
design (the original one lived in Paint-mixer's app-specific `auth.py`
and was intentionally left out — not broker infrastructure). Tokens
are issued from `cloud/dashboard/backend` instead: `POST
/api/admin/devices` (admin-JWT-protected) writes directly into this
service's `User` table over a second, dedicated DB connection
(`BROKER_DATABASE_URL` on the dashboard backend) and returns the
generated token exactly once. See `cloud/dashboard/README.md`
"Device token issuance" for the full flow and the frontend form.

That means right after this service's dedicated Postgres is first
created, its `User` table is empty until someone calls that endpoint
at least once — `check_device_token` rejects everything until then.
The issued token is what goes into `edge/small_scope/config.js`'s
`mqtt.deviceToken` for the gateway to authenticate.

A `User.enabled` column (default `true`) acts as a remote kill-switch:
`check_device_token` rejects a disabled device's credentials exactly
like a wrong token (same failure shape, no separate error path), so
an admin can instantly cut off a compromised or retired device
without rotating its token. Listing issued devices and toggling
`enabled` is done from `cloud/dashboard/backend` (`GET`/`PATCH
/api/admin/devices[/{email}]`) — see its README for the full flow.

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

## Running the MQTT smoke test

`tests/test_smoke.py` connects two MQTT clients over TLS against a running
broker instance, confirms a publish/subscribe round-trip, and confirms that
wrong device-token credentials get rejected with a bad-username/password
CONNACK. It's a script, not a `pytest` suite — run it directly.

Prerequisites:

1. A broker instance running — either `python scripts/run_local_stack.py up`
   (see that script) or the Docker setup below.
2. A device-token row in that broker's Postgres — either call `POST
   /api/admin/devices` on a running dashboard backend (see "Device token
   issuance" above), or insert one directly for a quick throwaway test,
   matching the username/token you'll pass the test.
3. A generated TLS cert/key pair (see the `openssl` command under
   "Deploying to Railway" step 3) — generate one locally, point
   `MQTT_TLS_CERT`/`MQTT_TLS_KEY` at it when starting the broker, and pass
   the cert's path to the test as `MQTT_TLS_CA_CERT`. Do not commit these
   files.

Install the test's only extra dependency and run it:

```bash
pip install -r tests/requirements.txt
MQTT_HOST=localhost \
MQTT_PORT=18830 \
MQTT_TLS_CA_CERT=/path/to/broker.crt \
MQTT_USERNAME=test@example.com \
MQTT_DEVICE_TOKEN=testtoken123 \
python tests/test_smoke.py
```

All env vars have localhost-oriented defaults except `MQTT_TLS_CA_CERT`,
which is required. See the module docstring in `tests/test_smoke.py` for the
full list.

## Deploying to Railway

Declared in `railway.toml` at this folder's root, built from
`Dockerfile`. Deploy this into the **same Railway project** as
`cloud/dashboard`'s services, since this service and `dashboard-backend`
share project-level variables (see "Railway Shared Variables" below).
Step by step, from scratch:

1. **Add the service.** In the project already created for
   `cloud/dashboard` (or create one first if deploying the broker
   alone), **New Service** → **GitHub Repo**, pick this repo. Set
   **Root Directory** to `cloud/broker` (Settings → Source) and
   **Dockerfile Path** to `Dockerfile` (Settings → Build). **Don't put
   the subfolder in both fields** — Root Directory `/cloud/broker` +
   Dockerfile Path `Dockerfile` is correct; Root Directory
   `/cloud/broker` + Dockerfile Path `/cloud/broker/Dockerfile` breaks
   the build (`failed to compute cache key ...
   "/requirements.txt": not found`, or the equivalent for this
   service's own files) because the build context no longer lines up
   with where the Dockerfile's `COPY` instructions expect it — this is
   exactly what happened on the `cloud/dashboard/backend` deploy, see
   its README. Name the service to match `railway.toml`.

2. **Provision this service's own Postgres.** **New** → **Database**
   → **Add PostgreSQL**, *inside this project* but as its own plugin —
   do not reuse the dashboard's Postgres (see "Database: dedicated,
   not shared" above). On this service's **Variables** tab, add
   `DATABASE_URL` referencing that plugin via Railway's variable
   picker. **Do this before the first deploy** — `broker.py`/`main.py`
   read `DATABASE_URL` at startup with no fallback, same as
   `cloud/dashboard/backend`'s `models.py`, so deploying without it set
   crashes immediately (`KeyError: 'DATABASE_URL'` in `railway logs`)
   even if the build itself succeeded. No manual migration step is
   needed beyond that — the Dockerfile's `CMD` runs `npx prisma migrate
   deploy` on every deploy.

3. **Set `MQTT_PORT`** (per-service, e.g. `1883`) and generate the
   broker's self-signed TLS cert/key pair, setting `MQTT_TLS_CERT` /
   `MQTT_TLS_KEY` as this service's own variables (`MQTT_TLS_KEY` must
   stay broker-only, never shared — see below). The cert's CN/SAN must
   be the TCP Proxy hostname from step 5 (e.g.
   `viaduct.proxy.rlwy.net`), not `localhost` — a cert minted before
   that hostname exists can be regenerated once it is known.

   **Generate the pair** with `scripts/generate_broker_cert.py` — pure
   Python (the `cryptography` package), so it works on Windows without
   `openssl` on PATH. It normalizes common copy-paste mistakes (a
   `mqtts://` scheme prefix, a trailing `:port`, a trailing slash) out
   of the host you give it, and writes the pair to `scripts/.broker-
   cert/` (gitignored):

   ```bash
   python scripts/generate_broker_cert.py --host viaduct.proxy.rlwy.net
   # On Windows PowerShell, running the .py file directly via `&` opens
   # it by file association instead of executing it — use the wrapper:
   # & 'scripts\generate_broker_cert.ps1' --host viaduct.proxy.rlwy.net
   ```

   It prints both files' full PEM content at the end, ready to paste
   directly into Railway's variable fields — **paste the exact block
   including the `BEGIN`/`END` lines**; a partial paste (e.g. only the
   start of a PowerShell command line pasted by mistake) produces a
   broker that crashes with `ssl.SSLError: [X509: KEY_VALUES_MISMATCH]`
   on boot if the cert and key end up from two different generation
   runs — verify a live pair matches by comparing MD5 of their modulus:
   `openssl x509 -noout -modulus -in broker.crt | openssl md5` must
   equal `openssl rsa -noout -modulus -in broker.key | openssl md5`.

   If `openssl` is available (e.g. Git Bash on Windows, or any
   Linux/macOS shell), the equivalent one-liner also works:

   ```bash
   openssl req -x509 -newkey rsa:2048 -nodes \
     -keyout broker.key -out broker.crt \
     -days 365 -subj "/CN=viaduct.proxy.rlwy.net" \
     -addext "subjectAltName=DNS:viaduct.proxy.rlwy.net"
   ```

   Either way, `broker.crt` goes in `MQTT_TLS_CERT` here (and in
   `MQTT_TLS_CA_CERT` on the dashboard side), `broker.key` goes in
   `MQTT_TLS_KEY` here only, never shared. Paste each file's **full
   contents** (not a path) into Railway's variable value — see "TLS
   model" above for why a path doesn't work on Railway.

   **What this automates and what it doesn't:** generating the files
   and printing their contents can be scripted/copy-pasted as above.
   Actually entering those values into Railway's project-level Shared
   Variables or a service's own env vars, signing in to the Railway
   account (OAuth/`railway login`), and provisioning the Postgres
   plugin in step 2 all require a human acting in the Railway dashboard
   or an already-authenticated `railway` CLI session — none of that can
   be done by running a local command.

4. **Deploy** — push to the linked branch or `railway up` from this
   folder. Railway's health check hits `GET /health` on `$PORT`
   automatically (`healthcheckPath` in `railway.toml`); confirm it goes
   healthy before continuing.

5. **Add the TCP Proxy.** Once healthy, open this service's
   **Settings → Networking → TCP Proxy**, and point it at `MQTT_PORT`.
   Railway returns a public `host:port` pair — that is the broker's
   real reachable address for MQTT clients. This step cannot be done
   before the service exists and is not declarative in `railway.toml`.

6. **Publish the shared variables.** With the TCP Proxy's `host:port`
   and the cert content from step 3 in hand, go to the **project's**
   **Settings → Shared Variables** and set `MQTT_URL` (built from the
   proxy host:port, `mqtts://host:port`) and a shared cert variable
   (e.g. `MQTT_TLS_CERT_PEM`, same content as this service's
   `MQTT_TLS_CERT`). Then switch to `cloud/dashboard`'s walkthrough
   (its README, step 4) to wire `dashboard-backend` to reference them.

7. **Issue at least one device token** by calling `POST
   /api/admin/devices` on the deployed dashboard backend (see "Device
   token issuance" above) before any client, dashboard backend's own
   MQTT ingest included, can authenticate.

Two distinct ports are involved in this service once deployed, and
**neither of them is Railway's injected `$PORT`**:

- **`HTTP_PORT`** (env var, default `8080`) — what uvicorn itself
  binds, serving only `GET /health` for Railway's deploy health check.
  Must match Settings → Networking → Public Networking → Target port.
- **`MQTT_PORT`** (env var, default `1883`) — the actual MQTT
  listener, a plain `asyncio` TCP server in the same process. Needs
  its own **Railway TCP Proxy** (Settings → Networking → TCP Proxy,
  pointed at `MQTT_PORT`) since Railway's HTTP domain doesn't expose
  raw TCP. Railway hands back a proxy `host:port` pair — that's the
  address clients (`MQTT_URL` on the dashboard side, the edge gateway)
  actually connect to.

**Why not just use Railway's `$PORT`?** On a service that has *both* a
public HTTP domain and a TCP Proxy, Railway's injected `$PORT` tracks
the TCP Proxy's target port (here, `MQTT_PORT`'s value), not the HTTP
domain's. Binding uvicorn to `$PORT` made it try to bind the exact same
port as the MQTT listener in the same process — uvicorn would crash
immediately after `Application startup complete`, Railway's restart
policy would spin the container back up, and it would crash again,
every few seconds, forever. `HTTP_PORT` is a separate, fixed env var
specifically to avoid this — don't switch uvicorn back to `$PORT`.

Required env vars (see `env.example`):

- `DATABASE_URL` — this service's own dedicated Postgres plugin
  (see "Database: dedicated, not shared" above). Service-specific,
  not a Railway Shared Variable.
- `HTTP_PORT` — port uvicorn's own HTTP server binds to (default
  `8080`). See "Two distinct ports" above for why this exists instead
  of using Railway's `$PORT`.
- `MQTT_PORT` — port the MQTT listener binds to internally.
- `MQTT_TLS_CERT` / `MQTT_TLS_KEY` — self-signed cert + key for
  `mqtts://`, either a file path or the PEM content itself (see "TLS
  model" above). Once deployed, fetch this cert (or its fingerprint) so
  it can be pinned on the client side (`MQTT_TLS_CA_CERT` for the
  dashboard backend) — do not fabricate or assume a value.
- `MQTT_TOPIC_PREFIX` / `MQTT_COMMAND_SUFFIX` — optional, default
  `plant/` / `/command`. See "Topic ACL" above; only change these if
  this broker ever serves topics outside `edge/small_scope`'s
  `plant/...` namespace.

### Env vars at a glance

A documentation aid on top of `env.example` — where each value
actually comes from when deploying this service to Railway:

| Var | Scope | Where the value comes from |
|---|---|---|
| `DATABASE_URL` | per-service | Auto-populated by referencing this service's own Postgres plugin (step 2) — don't hand-type it. |
| `HTTP_PORT` | per-service | Your own choice (default `8080`); must match Settings → Networking → Public Networking → Target port. Not `$PORT` — see "Two distinct ports" above. |
| `MQTT_PORT` | per-service | Your own choice (e.g. `1883`); must match what you point the TCP Proxy at in step 5. |
| `MQTT_TLS_CERT` | per-service here, **same content** as the shared cert | Output of `scripts/generate_broker_cert.py` (`broker.crt`), pasted in as its full PEM content. |
| `MQTT_TLS_KEY` | per-service, never shared | Output of `scripts/generate_broker_cert.py` (`broker.key`) — broker-only, full PEM content. |
| `MQTT_URL` (dashboard-side) | shared | Built from the TCP Proxy `host:port` Railway returns in step 5 (`mqtts://host:port`); published as a project Shared Variable in step 6. |
| `MQTT_TLS_CA_CERT` (dashboard-side) | shared, same content as `MQTT_TLS_CERT` | Same `broker.crt` content from above, published as a project Shared Variable in step 6. |
| `MQTT_USERNAME` / `MQTT_DEVICE_TOKEN` (dashboard-side) | per-service, per-client | Returned by `POST /api/admin/devices` (step 7 — see "Device token issuance"); `BROKER_DATABASE_URL` on the dashboard backend is what lets that endpoint write into this service's `User` table. |

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

Per-service, NOT shared: each service's own `DATABASE_URL` (separate,
dedicated Postgres instances), `MQTT_TLS_KEY` (broker's private key),
and any individual device token / `MQTT_USERNAME` /
`MQTT_DEVICE_TOKEN` a specific client uses to authenticate — those are
per-client credentials, not architecture-level config, and don't
belong in a project-wide shared variable.

**`BROKER_DATABASE_URL` (on the dashboard backend) is a special
case — NOT a Shared Variable, but still crosses the service
boundary.** It's this service's `DATABASE_URL` value, duplicated
as a second connection string on `cloud/dashboard/backend` solely so
`POST /api/admin/devices` can write into this service's `User` table.
It isn't shared via Railway's Shared Variables mechanism because it
is only ever consumed by that one endpoint on that one other
service — reference this service's Postgres plugin directly from the
dashboard backend's own Variables tab (Railway's variable picker can
reference a plugin from a different service in the same project),
rather than hand-copying the connection string.

This Dockerfile/service is written for POC stage — review resource
limits/health checks before relying on this for anything beyond a demo.
