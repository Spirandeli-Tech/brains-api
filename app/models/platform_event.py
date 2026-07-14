import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


class PlatformEvent(Base):
    """A single entry in the proactive-platform ledger.

    The Brains API is the control plane: every status transition the existing
    services (automations, code review, address-pr, implementations) already
    make gets mirrored here as one row, via `emit_event`. This table is the
    single source the /briefing endpoint, the unread badge, and (later) Slack
    all read from — no channel re-aggregates the run tables directly.
    """

    __tablename__ = "platform_events"

    __table_args__ = (
        Index("ix_platform_events_occurred_at", "occurred_at"),
        Index("ix_platform_events_seen_at", "seen_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # implementation | code_review | address_pr | automation | watcher | system
    source = Column(String, nullable=False)
    # run_started | run_finished | run_failed | awaiting_approval | proposal_created | watcher_alert
    event_type = Column(String, nullable=False)

    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    connection_name = Column(String, nullable=True)

    # Points back at the run/proposal that produced this event.
    ref_kind = Column(String, nullable=True)
    ref_id = Column(String, nullable=True)
    url_path = Column(String, nullable=True)

    # Null = unread. Drives the menu badge; set when the briefing page is opened.
    seen_at = Column(DateTime(timezone=True), nullable=True)
