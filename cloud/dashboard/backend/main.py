from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import engine, Base, PlcState
import mqtt_ingest
from auth import create_access_token, require_auth, verify_credentials

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
    allow_methods=["GET"],
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
