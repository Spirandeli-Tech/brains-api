import uuid
from datetime import datetime, time

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Time, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.db import Base


class RecurringTask(Base):
    __tablename__ = "recurring_tasks"

    __table_args__ = (
        Index("ix_recurring_tasks_user_id", "user_id"),
        Index("ix_recurring_tasks_enabled", "enabled"),
        Index("ix_recurring_tasks_task_type", "task_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    task_type = Column(String, nullable=False)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    frequency = Column(String, nullable=False)
    day_of_month = Column(Integer, nullable=True)
    day_of_week = Column(Integer, nullable=True)
    time_of_day = Column(Time, nullable=False, default=time(8, 0))
    enabled = Column(Boolean, nullable=False, default=True)
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    executions = relationship(
        "TaskExecution",
        back_populates="recurring_task",
        cascade="all, delete-orphan",
        order_by="TaskExecution.scheduled_for.desc()",
    )
