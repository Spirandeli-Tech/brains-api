from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String

from app.core.db import Base


class RunnerHeartbeat(Base):
    """Liveness signal written by each runner on every poll iteration.

    Lets the UI tell "runner idle" apart from "runner dead": the overview
    endpoint compares last_seen_at against now and marks the runner offline
    once the gap exceeds a small multiple of its poll interval. One row per
    runner_id (upserted), so it never grows unbounded.
    """

    __tablename__ = "runner_heartbeats"

    runner_id = Column(String, primary_key=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    poll_interval = Column(String, nullable=True)
    dry_run = Column(Boolean, nullable=True)
    version = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
