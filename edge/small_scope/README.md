# IOT small_scope — remote ON/OFF of one PLC output

> **Edge half:** this folder runs only on the SIMATIC IOT2050, with
> local plant-network access to the PLC's OPC UA server — it is never
> deployed to Railway. See `../../cloud/dashboard/` for the
> Railway-deployable half.

Minimal scope: an MQTT command (`"ON"`/`"OFF"`) on a single topic turns
one PLC output tag on or off, via OPC UA, running on the SIMATIC
IOT2050 gateway. No telemetry, no other tags, no interlock — the
smallest possible slice of the full architecture in
`../../Arquitecture.md`, same spirit as `LAB/LAB 4/small_scope`.

> **Status: PLC/OPC UA side confirmed working end-to-end.** Verified
> with a real external OPC UA client (UaExpert) connecting to the
> actual CPU over the network and reading `Q_RemoteOutput` live — see
> "Verified test (UaExpert)" below for exactly what was proven and how.
> The remaining open piece is the Railway/Paint-mixer broker's TLS
> support (tracked in that repo, not here).

## Planned: cloud dashboard (not yet built, separate repo)

Not implemented yet — documented here so the plan is visible without
digging through chat history. Full detail (if still present) was last
tracked in a Claude Code plan file at
`C:\Users\lcdan\.claude\plans\recursive-plotting-mountain.md`.

The dashboard will live in a **brand-new, separate local git repo** —
not inside `INDUSTRIAL-AUTOMATION` and not inside `Paint-mixer`. Scope:

1. **Broker TLS fix** (in the existing `Paint-mixer` repo, not the new
   one): wrap `api/broker.py`'s raw `asyncio.start_server()` with an
   `ssl.SSLContext`, and remove `auth_callback = check_device_token`
   from `api/main.py` so the broker is TLS-only, no device-token auth
   — matching this gateway's `config.js`/`index.js`, which already
   connect with no username/password.
2. **Postgres DB** — minimal schema to store current + historical
   input/output state, e.g. a single `plc_state` table
   (`id, tag_name, value, updated_at`), fed by subscribing to the
   broker's `plant/small_scope/output/state` topic and a new
   input-state topic (see "Planned input read" below).
3. **Angular frontend** — read-only dashboard showing current
   input/output values. Explicitly **no control/write-back UI, no
   HMI** for now — display only.

### Planned input read (small_scope side, not yet built)

In addition to the existing `Q_RemoteOutput` write path, this gateway
will also read a new placeholder input tag, `I_RemoteStatus` (Bool,
`%I3.0`), exposed directly via OPC UA as a plain tag (no FB needed —
the reliability issue seen earlier was specific to *writing* a plain
tag, not reading one). The gateway will poll it and publish changes to
a new MQTT topic (e.g. `plant/small_scope/input/state`) for the
dashboard above to consume.

## Verified test (UaExpert) — what was actually proven, and how

Test project: `IOT-TEST-FINAL`, CPU `1512SP F-1 PN`, tag `Q_RemoteOutput`
(`%Q0.3`, Bool) in the default tag table.

### The real blocker: a missing CPU license, not a config bug

The OPC UA server would start and accept client connections/sessions
from the very beginning, but the address space stayed structurally
present and **empty** — `Outputs` (and every other default folder)
contained nothing but a decorative `Icon` node, no matter how the tag's
Access/Writable checkboxes or OPC UA data-access settings were set.

Root cause, found in CPU Properties → **Runtime licenses → OPC UA**:
`Type of required license: SIMATIC OPC UA S7-1500 small` vs.
`Type of purchased license: No license` (shown in red, with a tooltip:
*"The selected OPC UA license is not sufficient..."*). Checked via
Automation License Manager (ALM) across the full installed license
list (9-page export, every WinCC/STEP7/SINAMICS/Process-Historian
license on the machine) — genuinely **not present**. `Process
Historian OPC UA Server`/`Data Logger` and `S7 OPC REDUNDANCY` are
different products and don't satisfy this requirement.

**Fix:** the license was found and installed from a separate ALM
"Yellow Disk" key-image source (3905 available keys, searched for
"OPC UA" the same way the existing "Find 150 'STEP'" saved search
worked). Once installed, TIA Portal's CPU properties page immediately
showed `Type of purchased license: SIMATIC OPC UA S7-1500 small`
with no red/error state — no manual selection needed, TIA detected it
automatically.

### Confirming it actually worked

1. Recompiled (0 errors) and downloaded to the device — "Loading
   completed (errors: 0; warnings: 0)".
2. Connected with **UaExpert** (Unified Automation's OPC UA test
   client) to `opc.tcp://192.168.0.3:4840`, no security (`None` policy,
   Anonymous), trusted the PLC's self-signed server certificate on
   first connect.
3. Browsed `PLC_1 → Outputs` in the live address space — **`Q_RemoteOutput`
   is now present** alongside the folder's `Icon` node (previously the
   folder was empty except `Icon`). Confirmed via the References panel
   too: `Organizes → Q_RemoteOutput`.
4. Dragged `Q_RemoteOutput` from the Address Space tree into UaExpert's
   Data Access View grid to watch/write its live value — this is the
   exact same read/write path the Node.js gateway's `node-opcua-client`
   will use.

This proves the entire PLC↔OPC UA leg of the architecture end-to-end,
independent of the gateway code — any further troubleshooting from
here is on the gateway/broker side, not the PLC side.

### Judgment call worth double-checking

Security policy used for this test was `None` (no encryption, Anonymous
auth) — fine for a first connectivity test on a trusted plant network,
but the earlier TIA Portal compile warnings explicitly flagged
"unsecured communication is permitted" and "access without user
authentication is permitted." Before this goes beyond a lab test,
switch the OPC UA server (and the gateway's `node-opcua-client` config)
to `Basic256Sha256` and a non-anonymous identity.

## What this needs on the PLC side (TIA Portal, one-time)

See `TagTable_IoTOutput.md` for the exact tags to create — this scope
now has two: `Q_RemoteOutput` (write, via `FB_RemoteOutput`) and
`I_RemoteStatus` (read-only, plain tag, no FB — the write reliability
issue below never showed up on reads). In short:

1. Create `Q_RemoteOutput` (Bool, any free `%Q` address — `%Q3.0` if
   loading alongside LAB4/LAB5 in the same project, since LAB5 already
   uses all of `%Q2.x`; the verified test project used `%Q0.3` in a
   standalone project with no collision to worry about) in the default
   tag table — **no FB, no OB1 call needed** for this minimal scope.
   OPC UA writes directly to the output's process image; nothing else
   in the program needs to touch this tag. Leave its "Accessible from
   HMI/OPC UA/Web API" checkbox checked (default).
2. Enable the OPC UA server on the S7-1500 CPU (Device configuration →
   CPU properties → OPC UA → enable, default port 4840).
3. **Check CPU Properties → Runtime licenses → OPC UA before anything
   else.** If `Type of purchased license` shows "No license" (in red),
   the server will start and connect but the address space stays
   empty no matter what else is configured — see "Verified test"
   below for the full story. This was the actual blocker in testing
   and is easy to miss since everything else looks fine until you
   check this one page.
4. No manual "OPC UA data access view"/"Server interface" needed —
   confirmed in testing that a plain tag with Access/Writable checked
   is auto-exposed once the license is present. Browse the live server
   (e.g. with UaExpert) to find the exact NodeId TIA Portal assigned —
   copy that into `config.js`'s `opcua.outputNodeId` rather than
   assuming the string.
5. Create `I_RemoteStatus` (Bool, `%I3.0`) in the default tag table —
   also no FB, no OB1 call needed. Browse the live server for its
   NodeId and copy it into `config.js`'s `opcua.inputNodeId`.
6. Compile, download. Confirm the CPU has a static IP on the plant
   network the IOT2050 can reach (no internet-facing config needed on
   the PLC — see `../../Arquitecture.md`).

See `TIA_PORTAL_BUILD_GUIDE.md` for the full click-by-click version of
the steps above, including the license check and NodeId-browsing
verification checklist.

## MQTT broker: reused from the Paint-mixer project, TLS + device-token auth

This doesn't stand up a separate broker — it connects to the custom
embedded MQTT broker already running inside the `Paint-mixer` repo's
FastAPI app (`api/broker.py` + `api/main.py`), deployed on Railway.
**Auth model: TLS is added on top of the existing device-token auth,
not a replacement for it.** The broker still runs
`check_device_token(email, token)` on every CONNECT — this gateway
sends its account email as the MQTT username and that account's
device token (from Paint-mixer's `GET /api/auth/device-token`) as the
MQTT password, same fields `check_device_token` already validates.

**This requires a broker-side change that is NOT part of this repo —
tracked separately in `Paint-mixer`:**
- `api/broker.py` currently has **zero TLS support** — it's a raw
  `asyncio.start_server()` with no SSL context at all. It needs to be
  wrapped with an `ssl.SSLContext` (cert + key) before this gateway can
  connect to it over `mqtts://`. (This part is done in that repo's
  working tree, awaiting review/commit there.)
- `api/main.py`'s `auth_callback = check_device_token` line **stays as
  it is** — do not remove it. TLS and device-token auth run together.
- Still listens on `MQTT_PORT` (env var, default `1884`) — a
  **different port from the HTTP API's `$PORT`**, needing its own
  Railway **TCP Proxy** to be reachable from here. If Railway's TCP
  Proxy terminates TLS for you, the broker-side `ssl` wrapping above
  may not even be needed — confirm which is the case before assuming
  `api/broker.py` needs edits.
- Topics are free-form (no per-topic ACL) — this gateway uses its own
  `plant/small_scope/...` topics, distinct from the paint-mixer's
  `mixer/command`/`mixer/status`, so the two don't collide on the same
  broker.

**Cert trust (self-signed, not CA-issued):** the broker's TLS
certificate is self-signed and trusted manually — same posture as the
OPC UA leg's `endpointMustExist: false` — so standard CA validation
will always fail against it. Fetch that exact certificate once (e.g.
`openssl s_client -connect <host>:<port> -showcerts`, save the server
cert as PEM) and point `MQTT_TLS_CA_FILE` at it so `mqtt.js`'s `ca`
option pins that specific cert as the trust anchor. Leaving
`MQTT_TLS_CA_FILE` unset falls back to `rejectUnauthorized: false` (no
cert validation at all, logged as a warning on startup) — acceptable
for this lab/POC stage, not beyond it.

## Setup (on the SIMATIC IOT2050)

```bash
cd IOT/small_scope
npm install
```

Edit `config.js`, or set these as environment variables instead:
- `opcua.endpointUrl` — the PLC's OPC UA endpoint (`opc.tcp://<plc-ip>:4840`).
- `opcua.outputNodeId` — the NodeId of the output tag from TIA Portal.
- `MQTT_URL` — `mqtts://<paint-mixer-app>.up.railway.app:<TCP-proxy-port>`
  (TLS — requires the broker-side TLS change noted above to actually
  work).
- `MQTT_USERNAME` / `MQTT_DEVICE_TOKEN` — account email + device token,
  sent as the MQTT CONNECT username/password (the broker still
  requires `check_device_token` auth; TLS doesn't replace it).
- `MQTT_TLS_CA_FILE` — path to the broker's self-signed cert PEM, so
  the client trusts that specific cert. Unset falls back to
  `rejectUnauthorized: false` (no validation), lab/POC only.
- `mqtt.commandTopic` / `mqtt.stateTopic` — topic names to use.
- `opcua.inputNodeId` / `opcua.inputPollMs` — the input tag's NodeId
  and poll interval.
- `mqtt.inputStateTopic` — topic the gateway publishes input changes to.

Run it:

```bash
npm start
```

## Behavior

- Publish `"ON"` or `"OFF"` (plain text) to `mqtt.commandTopic` → the
  gateway writes `TRUE`/`FALSE` to the configured PLC output tag over
  OPC UA.
- After each successful write, the gateway publishes the same value to
  `mqtt.stateTopic` — **not retained** (this broker doesn't support
  retained messages), so a subscriber only sees it if it's already
  connected and subscribed at the moment of the write, not on a late
  connect.
- Any other payload on the command topic is logged and ignored.
- Separately, the gateway polls `opcua.inputNodeId` (`I_RemoteStatus`)
  over OPC UA every `opcua.inputPollMs` (default 1000ms) and publishes
  `"ON"`/`"OFF"` to `mqtt.inputStateTopic` only when the read value
  changes from the last one it published — avoids republishing an
  identical value every poll.

## Running as a service (systemd, on the IOT2050's Debian)

```ini
[Unit]
Description=IOT small_scope gateway
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/iot-small-scope
ExecStart=/usr/bin/node index.js
Restart=on-failure
RestartSec=5
EnvironmentFile=-/opt/iot-small-scope/.env

[Install]
WantedBy=multi-user.target
```

Copy this folder to `/opt/iot-small-scope` on the IOT2050, run
`npm install --production` there, then enable/start the unit.

## Judgment calls / things to confirm

- No interlock between this remote write and any physical control of
  the same output — if the PLC logic already drives `Q_RemoteOutput`
  from somewhere else (a pushbutton, another FB), the two sources will
  race. Keep this tag dedicated to remote control only, or add
  explicit OR/arbitration logic in the FB if it needs to coexist with
  a physical source — not handled here, matches the "last write wins,
  no interlock" decision made for the broader architecture.
- TLS cert verification: `node-opcua-client`'s `OPCUAClient.create()` is
  using defaults here (`endpointMustExist: false`) for simplicity on a
  trusted plant network — tighten this if the OPC UA connection ever
  crosses an untrusted segment.
