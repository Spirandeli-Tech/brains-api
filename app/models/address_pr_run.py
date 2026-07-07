import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class AddressPrRun(Base):
    """A single "address PR comments" pipeline (draft+fix → approve → commit/push
    → approve → post replies).

    The Brains API is the control plane: stores run + steps, serves the UI.
    The host-side runner is the execution plane: claims queued runs, checks out
    the PR branch into an isolated worktree, runs /address-pr-comments in
    phases, pauses for approval twice, then commits/pushes and posts replies.
    """

    __tablename__ = "address_pr_runs"

    __table_args__ = (
        Index("ix_apr_runs_user", "created_by_user_id"),
        Index("ix_apr_runs_status", "status"),
        Index("ix_apr_runs_connection", "connection_id"),
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
    # Optional focus instructions (e.g. scope to a single comment/thread id).
    instructions = Column(Text, nullable=True)

    # queued | running | awaiting_approval | done | failed | cancelled
    status = Column(String, nullable=False, default="queued", server_default="queued")

    # Isolated git worktree for this PR — created by fix_draft, reused across
    # both approval pauses, removed once the run reaches a terminal status.
    # Non-null is also the signal a cancelled run still needs cleanup (mirrors
    # ImplementationRun.worktree_path).
    worktree_path = Column(String, nullable=True)
    # Actual PR head branch, discovered by fix_draft (not the runner).
    branch = Column(String, nullable=True)

    # Structured plan produced by fix_draft and mutated at each approval gate.
    # Schema: {items:[{id,path,line,reviewer,quote,verdict,summary,reply,
    #                   apply_fix,post_reply}], commit_message}
    fix_plan = Column(JSONB, nullable=True)

    error = Column(Text, nullable=True)

    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    connection = relationship("ProductivityConnection", lazy="joined")
    steps = relationship(
        "AddressPrStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AddressPrStep.position",
    )
