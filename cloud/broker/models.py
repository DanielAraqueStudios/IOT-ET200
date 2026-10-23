from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
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
    deviceToken  = Column(String,  nullable=True)
    createdAt    = Column(DateTime, default=func.now())
