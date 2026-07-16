import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class Watcher(Base):
    """Detects real-world state (a PR, a ticket) so the platform can react to it
    without waiting for the user to paste a link — see
    docs/features/proactive-platform/README.md, fase 2.

    `connection_id` mirrors CodeReviewRun/AddressPrRun/ImplementationRun: it
    points at the productivity_connections row whose display_name the runner
    matches against its local config.json to pick credentials/env — not a
    plain connection_name string like Automation uses.
    """

    __tablename__ = "watchers"

    __table_args__ = (
        Index("ix_watchers_user_id", "user_id"),
        Index("ix_watchers_enabled", "enabled"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # github_review_requested | github_reviews_received | jira_backlog_assigned
    kind = Column(String, nullable=False)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("productivity_connections.id", ondelete="SET NULL"),
        nullable=True,
    )
    config = Column(JSONB, nullable=False, default=dict, server_default="{}")
    interval_minutes = Column(Integer, nullable=False, default=10, server_default="10")
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    connection = relationship("ProductivityConnection", lazy="joined")
    sightings = relationship(
        "WatcherSighting",
        back_populates="watcher",
        cascade="all, delete-orphan",
    )
