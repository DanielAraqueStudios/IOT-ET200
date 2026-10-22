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
