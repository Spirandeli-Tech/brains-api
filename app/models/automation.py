import uuid
from datetime import datetime, time

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Time, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Automation(Base):
    __tablename__ = "automations"

    __table_args__ = (
        Index("ix_automations_user_id", "user_id"),
        Index("ix_automations_enabled", "enabled"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    skill = Column(String, nullable=False)
    connection_name = Column(String, nullable=True)
    work_dir = Column(String, nullable=True)
    frequency = Column(String, nullable=False)
    day_of_week = Column(Integer, nullable=True)
    day_of_month = Column(Integer, nullable=True)
    time_of_day = Column(Time, nullable=False, default=time(8, 0))
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    runs = relationship(
        "AutomationRun",
        back_populates="automation",
        cascade="all, delete-orphan",
        order_by="AutomationRun.scheduled_for.desc()",
    )
