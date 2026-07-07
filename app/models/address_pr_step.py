import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class AddressPrStep(Base):
    """One step of an address-PR run: fix_draft, commit_push, or post_replies."""

    __tablename__ = "address_pr_steps"

    __table_args__ = (
        Index("ix_apr_steps_run", "run_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("address_pr_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # fix_draft | commit_push | post_replies
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

    run = relationship("AddressPrRun", back_populates="steps")
