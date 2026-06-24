import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


class ImplementationRun(Base):
    """A single end-to-end ticket implementation pipeline.

    The Brains API is the control plane: it stores the run + its steps and
    serves them to the UI. The host-side runner is the execution plane: it
    claims queued runs, executes the steps (via `direnv exec claude` inside the
    org's directory) and patches status/logs back. No credential is ever stored
    here — only references (connection_id, ticket_key, worktree_path).
    """

    __tablename__ = "implementation_runs"

    __table_args__ = (
        Index("ix_impl_runs_user", "created_by_user_id"),
        Index("ix_impl_runs_status", "status"),
        Index("ix_impl_runs_connection", "connection_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # The org / connection this run belongs to. Reuses the existing
    # productivity connection as the org identity.
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("productivity_connections.id", ondelete="SET NULL"),
        nullable=True,
    )

    ticket_url = Column(String, nullable=False)
    ticket_key = Column(String, nullable=True)
    ticket_summary = Column(String, nullable=True)
    # Free-text guidance the user gives the agent at launch time.
    instructions = Column(Text, nullable=True)
    # Iteration notes appended mid-run (e.g. before approving open_pr).
    iteration_notes = Column(Text, nullable=True)

    # queued | running | awaiting_approval | done | failed | cancelled
    status = Column(String, nullable=False, default="queued", server_default="queued")

    repo_name = Column(String, nullable=True)
    base_branch = Column(String, nullable=True)

    worktree_path = Column(String, nullable=True)
    branch = Column(String, nullable=True)
    pr_url = Column(String, nullable=True)
    error = Column(Text, nullable=True)

    # Atomic claim by the runner (prevents duplicate work across runner instances).
    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    connection = relationship("ProductivityConnection", lazy="joined")
    steps = relationship(
        "ImplementationStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ImplementationStep.position",
    )
