import secrets
from contextlib import asynccontextmanager

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


class CreateDeviceResponse(BaseModel):
    email: str
    device_token: str


@app.post("/api/admin/devices", response_model=CreateDeviceResponse, status_code=201)
def create_device(body: CreateDeviceRequest, user: str = Depends(require_auth)):
    """Creates (or re-issues a token for) a device entry in the broker's
    User table. The returned device_token is shown exactly once — it is
    not retrievable again afterward, matching the broker's own
    check_device_token lookup, which only ever compares against the
    stored hash-equivalent value, never displays it back."""
    token = secrets.token_urlsafe(32)
    with Session(broker_engine) as s:
        existing = s.query(BrokerUser).filter_by(email=body.email).first()
        if existing:
            existing.deviceToken = token
        else:
            # passwordHash is unused by the broker's device-token auth
            # (check_device_token only compares deviceToken) but the
            # column is NOT NULL — fill it with an unusable placeholder
            # hash rather than a real password, since this is a
            # device entry, not a human login.
            s.add(BrokerUser(
                email=body.email,
                passwordHash=pwd_context.hash(secrets.token_urlsafe(32)),
                deviceToken=token,
            ))
        s.commit()
    return CreateDeviceResponse(email=body.email, device_token=token)
