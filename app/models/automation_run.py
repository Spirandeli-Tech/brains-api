import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, String, DateTime, Date, Text, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    __table_args__ = (
        # Scheduled (non-manual) runs are still limited to one per day; manual "Run now"
        # clicks are exempt so a user can trigger extra runs on top of the daily schedule.
        Index(
            "uq_automation_run_schedule_auto",
            "automation_id",
            "scheduled_for",
            unique=True,
            postgresql_where=text("NOT is_manual"),
        ),
        Index("ix_automation_runs_automation_id", "automation_id"),
        Index("ix_automation_runs_status", "status"),
        Index("ix_automation_runs_scheduled_for", "scheduled_for"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    automation_id = Column(
        UUID(as_uuid=True), ForeignKey("automations.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for = Column(Date, nullable=False)
    status = Column(String, nullable=False, default="pending")
    is_manual = Column(Boolean, nullable=False, default=False)
    log = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    claimed_by = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    automation = relationship("Automation", back_populates="runs")
