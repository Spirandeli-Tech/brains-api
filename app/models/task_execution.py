import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Date, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class TaskExecution(Base):
    __tablename__ = "task_executions"

    __table_args__ = (
        UniqueConstraint("recurring_task_id", "scheduled_for", name="uq_task_execution_schedule"),
        Index("ix_task_executions_recurring_task_id", "recurring_task_id"),
        Index("ix_task_executions_status", "status"),
        Index("ix_task_executions_scheduled_for", "scheduled_for"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recurring_task_id = Column(
        UUID(as_uuid=True), ForeignKey("recurring_tasks.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="pending")
    result_reference_id = Column(UUID(as_uuid=True), nullable=True)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    recurring_task = relationship("RecurringTask", back_populates="executions")
