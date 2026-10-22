import os
from sqlalchemy import create_engine, Column, BigInteger, Text, DateTime, func
from sqlalchemy.orm import declarative_base

DATABASE_URL = os.environ["DATABASE_URL"]  # e.g. postgresql://user:pass@host:5432/plc
engine = create_engine(DATABASE_URL)
Base = declarative_base()


class PlcState(Base):
    __tablename__ = "plc_state"

    id = Column(BigInteger, primary_key=True)
    tag_name = Column(Text, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
