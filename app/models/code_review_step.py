import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class CodeReviewStep(Base):
    """One step of a code review run: review_draft or post_review."""

    __tablename__ = "code_review_steps"

    __table_args__ = (
        Index("ix_cr_steps_run", "run_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("code_review_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # review_draft | post_review
    kind = Column(String, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    sensitive = Column(Boolean, nullable=False, default=False, server_default="false")

    # pending | running | awaiting_approval | done | failed | skipped
    status = Column(String, nullable=False, default="pending", server_default="pending")
    approved = Column(Boolean, nullable=False, default=False, server_default="false")
    log = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    run = relationship("CodeReviewRun", back_populates="steps")
