import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.db import Base


class PlannerRun(Base):
    """One day's "Insights for Today" plan — fase 4a of the proactive platform
    (docs/features/proactive-platform/fase4a-planejadora-jira.md).

    The Brains API is the control plane: it holds the run and, once ready, the
    generated narrative + the `proposals` (source="planner") the run produced.
    The host-side runner is the execution plane: it claims a queued run, reads
    every org's Jira board via `direnv exec <org>`, has Claude synthesize a
    PT-BR narrative + suggestions, and PATCHes them back.

    `plan_date` is unique per user — the idempotency key behind get-or-create.
    Both the scheduled path (materialize_planner_run in the scheduler) and the
    lazy/catch-up path (GET /insights when the Mac was off at the scheduled
    hour) converge on the same row, so a day never gets planned twice.
    """

    __tablename__ = "planner_runs"

    __table_args__ = (
        UniqueConstraint("user_id", "plan_date", name="uq_planner_runs_user_date"),
        Index("ix_planner_runs_status", "status"),
        Index("ix_planner_runs_user", "user_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    plan_date = Column(Date, nullable=False)

    # queued | running | done | failed
    status = Column(String, nullable=False, default="queued", server_default="queued")

    # The day's one-line thesis ("lead") Claude generated; null until finished.
    narrative = Column(Text, nullable=True)
    # Scannable judgment layer: [{org, text, tone}] — what actually matters
    # today, pulled out of the old wall-of-text narrative.
    highlights = Column(JSONB, nullable=True)
    # Per-org board data the runner collected, for the "Por org" UI block.
    board_summary = Column(JSONB, nullable=True)
    # Claude cost of this run's synthesis step (the runner captures it).
    claude_cost_usd = Column(Numeric(10, 4), nullable=True)

    error = Column(Text, nullable=True)

    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
