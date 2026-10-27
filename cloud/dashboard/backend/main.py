import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import engine, Base, PlcState
from broker_db import broker_engine, BrokerUser
import mqtt_ingest
from auth import create_access_token, require_auth, verify_credentials, pwd_context

Base.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = mqtt_ingest.start()
    yield
    client.loop_stop()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest):
    if not verify_credentials(body.username, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return LoginResponse(access_token=create_access_token(body.username))


@app.get("/api/health")
def health():
    """Unauthenticated status check for the frontend's corner widget.
    "broker" reflects this backend's own MQTT connection state (see
    mqtt_ingest.is_connected) rather than an independent HTTP check
    against the broker, since that's a more honest signal — two
    services that are each "up" but can't talk to each other is the
    failure mode this is meant to catch."""
    mqtt_connected = mqtt_ingest.is_connected()
    return {
        "backend": "up",
        "broker": "up" if mqtt_connected else "down",
        "mqtt_connected": mqtt_connected,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/state")
def current_state(user: str = Depends(require_auth)):
    """Latest value per tag_name — read-only, no write endpoints by design."""
    with Session(engine) as s:
        subq = (
            s.query(PlcState.tag_name, func.max(PlcState.id).label("max_id"))
            .group_by(PlcState.tag_name)
            .subquery()
        )
        rows = (
            s.query(PlcState)
            .join(subq, PlcState.id == subq.c.max_id)
            .all()
        )
        return [
            {"tag_name": r.tag_name, "value": r.value, "updated_at": r.updated_at.isoformat()}
            for r in rows
        ]


@app.get("/api/history/{tag_name:path}")
def tag_history(tag_name: str, limit: int = 100, user: str = Depends(require_auth)):
    with Session(engine) as s:
        rows = (
            s.query(PlcState)
            .filter(PlcState.tag_name == tag_name)
            .order_by(PlcState.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {"value": r.value, "updated_at": r.updated_at.isoformat()}
            for r in rows
        ]


# ── Device/MQTT token issuance ───────────────────────────────────────────────
# Admin-only (same JWT auth as the rest of this API). Writes into the
# BROKER's own Postgres (BrokerUser / broker_engine, see broker_db.py) —
# NOT this service's own DATABASE_URL — since that's the table the
# broker's check_device_token() actually reads. The returned token is
# the exact value to put into edge/small_scope's config.js
# (mqtt.deviceToken) for that device to authenticate to the broker.


class CreateDeviceRequest(BaseModel):
    email: str
    # Topic ACL (see cloud/broker/broker.py): whether this device may
    # PUBLISH to a "/command" topic. Defaults to False — only devices
    # that legitimately need to send commands (not just telemetry)
    # should be issued a token with this set.
    can_command: bool = False


class CreateDeviceResponse(BaseModel):
    email: str
    device_token: str
    can_command: bool


@app.post("/api/admin/devices", response_model=CreateDeviceResponse, status_code=201)
def create_device(body: CreateDeviceRequest, user: str = Depends(require_auth)):
    """Creates (or re-issues a token for) a device entry in the broker's
    User table. The returned device_token is shown exactly once — only
    its bcrypt hash is stored, matching the broker's own
    check_device_token, which verifies against that hash and never
    displays (or stores) the plaintext value."""
    token = secrets.token_urlsafe(32)
    token_hash = pwd_context.hash(token)
    with Session(broker_engine) as s:
        existing = s.query(BrokerUser).filter_by(email=body.email).first()
        if existing:
            existing.deviceToken = token_hash
            existing.canCommand = body.can_command
            # Re-issuing a token also clears any prior disable — the
            # admin explicitly asked for a working credential.
            existing.enabled = True
        else:
            # passwordHash is unused by the broker's device-token auth
            # (check_device_token only compares deviceToken) but the
            # column is NOT NULL — fill it with an unusable placeholder
            # hash rather than a real password, since this is a
            # device entry, not a human login.
            s.add(BrokerUser(
                email=body.email,
                passwordHash=pwd_context.hash(secrets.token_urlsafe(32)),
                deviceToken=token_hash,
                canCommand=body.can_command,
            ))
        s.commit()
    return CreateDeviceResponse(email=body.email, device_token=token, can_command=body.can_command)


class DeviceInfo(BaseModel):
    email: str
    can_command: bool
    enabled: bool
    created_at: str


@app.get("/api/admin/devices", response_model=list[DeviceInfo])
def list_devices(user: str = Depends(require_auth)):
    """Lists issued devices for the admin UI. Never returns deviceToken
    (or its hash) — that's a write-once secret by design (see
    create_device's docstring); this endpoint must not leak it even
    as a hash."""
    with Session(broker_engine) as s:
        rows = s.query(BrokerUser).order_by(BrokerUser.createdAt.desc()).all()
        return [
            DeviceInfo(
                email=r.email,
                can_command=bool(r.canCommand),
                enabled=bool(r.enabled),
                created_at=r.createdAt.isoformat() if r.createdAt else "",
            )
            for r in rows
        ]


class SetEnabledRequest(BaseModel):
    enabled: bool


@app.patch("/api/admin/devices/{email}", response_model=DeviceInfo)
def set_device_enabled(email: str, body: SetEnabledRequest, user: str = Depends(require_auth)):
    """Remote kill-switch: flips `enabled` for an already-issued device
    without touching its token. Does NOT accept or require a new
    token — re-enabling makes the existing (previously issued) token
    work again, which is the whole point versus re-issuing. 404s if
    the email has no device entry, rather than silently no-op'ing."""
    with Session(broker_engine) as s:
        existing = s.query(BrokerUser).filter_by(email=email).first()
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No device with that email")
        existing.enabled = body.enabled
        s.commit()
        return DeviceInfo(
            email=existing.email,
            can_command=bool(existing.canCommand),
            enabled=bool(existing.enabled),
            created_at=existing.createdAt.isoformat() if existing.createdAt else "",
        )
