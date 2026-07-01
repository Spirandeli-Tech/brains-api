import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class CodeReviewRun(Base):
    """A single PR code review pipeline (draft → human approval → post).

    The Brains API is the control plane: stores run + steps, serves the UI.
    The host-side runner is the execution plane: claims queued runs, runs
    /pr-review (draft phase), pauses for approval, then posts only the
    approved items.
    """

    __tablename__ = "code_review_runs"

    __table_args__ = (
        Index("ix_cr_runs_user", "created_by_user_id"),
        Index("ix_cr_runs_status", "status"),
        Index("ix_cr_runs_connection", "connection_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("productivity_connections.id", ondelete="SET NULL"),
        nullable=True,
    )

    pr_url = Column(String, nullable=False)
    pr_number = Column(String, nullable=True)
    repo_name = Column(String, nullable=True)
    ticket_key = Column(String, nullable=True)
    # Optional focus instructions for the review (e.g. "focus on performance").
    instructions = Column(Text, nullable=True)

    # queued | running | awaiting_approval | done | failed | cancelled
    status = Column(String, nullable=False, default="queued", server_default="queued")

    # Chosen at approval time: approve | request_changes | comment
    review_action = Column(String, nullable=True)
    # Structured review plan produced by review_draft and filtered by the user
    # at approval time. The post_review step posts exactly this.
    # Schema: {action, comments:[{path,line,side,body}], replies:[{comment_id,body}]}
    review_plan = Column(JSONB, nullable=True)

    error = Column(Text, nullable=True)

    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    connection = relationship("ProductivityConnection", lazy="joined")
    steps = relationship(
        "CodeReviewStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="CodeReviewStep.position",
    )
