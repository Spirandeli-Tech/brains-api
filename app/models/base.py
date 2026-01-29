from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.core.db import Base


class SystemMeta(Base):
    __tablename__ = "system_meta"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
