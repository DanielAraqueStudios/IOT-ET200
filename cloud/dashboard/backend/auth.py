"""Minimal JWT auth for the dashboard's REST API only.

Single admin credential from env vars — no user table, no refresh
tokens. The MQTT connection stays TLS-only/no-auth and is untouched by
this module.
"""
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60

ADMIN_USER = os.environ["DASHBOARD_ADMIN_USER"]
ADMIN_PASSWORD_HASH = os.environ["DASHBOARD_ADMIN_PASSWORD_HASH"]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def verify_credentials(username: str, password: str) -> bool:
    return username == ADMIN_USER and pwd_context.verify(password, ADMIN_PASSWORD_HASH)


def create_access_token(username: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expires_at}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> str:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload["sub"]
