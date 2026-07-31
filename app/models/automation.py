import uuid
from datetime import datetime, time

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, Time, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    instructions = Column(Text, nullable=True)
    connection_name = Column(String, nullable=True)
    repo_name = Column(String, nullable=True)
    claude_model = Column(String, nullable=True)
    frequency = Column(String, nullable=False)
    day_of_week = Column(Integer, nullable=True)
    day_of_month = Column(Integer, nullable=True)
    days_of_week = Column(JSONB, nullable=True)
    time_of_day = Column(Time, nullable=False, default=time(8, 0))
    enabled = Column(Boolean, nullable=False, default=True)
    # When true, the runner pauses this automation after its prepare phase (phase 1)
    # instead of completing: the run goes to `awaiting_approval` and shows up on the
    # "Aguardando você" board. Approving it re-enqueues the same run as phase 2, which
    # runs to completion. Used by /devocional-preparar-semana (prepare → approve → publish).
    requires_approval = Column(Boolean, nullable=False, default=False, server_default="false")
    # Ad-hoc automation created to dispatch a one-off skill run (e.g. a planner
    # proposal's `run_skill`). Never self-schedules (enabled=False, frequency
    # "manual") and is hidden from the Automations UI list. Reuses the whole
    # automation runner path without a new run type.
    ephemeral = Column(Boolean, nullable=False, default=False, server_default="false")
    # Free-form context carried by ephemeral runs. For Slack-sourced dispatches it
    # holds {"source":"slack","slack_channel":…,"slack_ts":…} so the completion hook
    # can reply on the right DM/thread without trusting the LLM to echo it back.
    meta = Column(JSONB, nullable=True)
    # User-assigned free-form labels for organizing the Automations list (multi-select,
    # e.g. ["finance","content"]). Not derived from anything (skill/slug), purely manual.
    tags = Column(JSONB, nullable=True, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    runs = relationship(
        "AutomationRun",
        back_populates="automation",
        cascade="all, delete-orphan",
        order_by="AutomationRun.scheduled_for.desc(), AutomationRun.created_at.desc()",
    )
