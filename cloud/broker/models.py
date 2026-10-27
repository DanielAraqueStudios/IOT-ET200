from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import DeclarativeBase
import os
from dotenv import load_dotenv
from pathlib import Path

_here = Path(__file__).parent
load_dotenv(_here / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)


class Base(DeclarativeBase):
    pass


class User(Base):
    """Only the columns the broker's device-token auth needs to read.
    Must match the `User` table of whichever service issues device
    tokens (see cloud/broker/README.md)."""
    __tablename__ = "User"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    email        = Column(String,  unique=True, nullable=False)
    passwordHash = Column(String,  nullable=False)
    # Bcrypt hash of the device token (never the plaintext token itself —
    # see auth.py:check_device_token, which verifies against this hash).
    deviceToken  = Column(String,  nullable=True)
    # Topic-ACL flag: only identities with canCommand=True may PUBLISH to
    # topics ending in "/command" (see broker.py's SUBSCRIBE/PUBLISH ACL).
    canCommand   = Column(Boolean, nullable=False, default=False)
    # Remote kill-switch: when False, check_device_token() rejects this
    # device's credentials outright (same failure shape as a bad token),
    # without needing to rotate/re-issue the token.
    enabled      = Column(Boolean, nullable=False, default=True)
    createdAt    = Column(DateTime, default=func.now())
