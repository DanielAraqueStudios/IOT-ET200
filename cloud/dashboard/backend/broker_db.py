"""Second DB connection, scoped only to device-token issuance.

This backend's own DATABASE_URL (models.py) is the dashboard's
Postgres (plc_state). This module is a SEPARATE connection to the
broker's dedicated Postgres (cloud/broker's DATABASE_URL), used only
by the device-issuance endpoint in main.py — the two databases are
never merged.

The `User` table shape here must stay in sync with cloud/broker's
Prisma-managed schema (cloud/broker/prisma/schema.prisma), which is
the source of truth — this is a mirror, not an independent
definition. If that schema changes, update this file to match.
"""
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.orm import DeclarativeBase

BROKER_DATABASE_URL = os.environ["BROKER_DATABASE_URL"]
broker_engine = create_engine(BROKER_DATABASE_URL)


class BrokerBase(DeclarativeBase):
    pass


class BrokerUser(BrokerBase):
    """Mirrors cloud/broker/prisma/schema.prisma's User model exactly."""
    __tablename__ = "User"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    email        = Column(String,  unique=True, nullable=False)
    passwordHash = Column(String,  nullable=False)
    # Bcrypt hash of the device token — see main.py:create_device, which
    # hashes before storing and returns the plaintext token only once.
    deviceToken  = Column(String,  nullable=True)
    canCommand   = Column(Boolean, nullable=False, default=False)
    # Remote kill-switch — see main.py's PATCH /api/admin/devices/{email}.
    # When False, the broker's check_device_token() rejects this
    # device's credentials without needing the token rotated.
    enabled      = Column(Boolean, nullable=False, default=True)
    createdAt    = Column(DateTime, default=func.now())
