import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class ImplementationStep(Base):
    """One step of an implementation run, e.g. open_pr or code_review.

    `sensitive` steps cause the runner to pause and set status to
    'awaiting_approval' until the user approves from the UI.
    """

    __tablename__ = "implementation_steps"

    __table_args__ = (
        Index("ix_impl_steps_run", "run_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("implementation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # implement | open_pr | code_review | address_feedback | qa_notes | move_card
    kind = Column(String, nullable=False)
    # Execution order within the run.
    position = Column(Integer, nullable=False, default=0)
    sensitive = Column(Boolean, nullable=False, default=False, server_default="false")

    # pending | running | awaiting_approval | done | failed | skipped
    status = Column(String, nullable=False, default="pending", server_default="pending")
    # Set when the user approves a sensitive step. The runner then executes it
    # (instead of pausing again) on the next claim.
    approved = Column(Boolean, nullable=False, default=False, server_default="false")
    log = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    run = relationship("ImplementationRun", back_populates="steps")
