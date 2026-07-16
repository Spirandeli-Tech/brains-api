import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.db import Base


class Proposal(Base):
    """A suggestion the platform makes that a human must accept or dismiss.

    The Brains API is the control plane: it only stores the suggestion and
    dispatches it, on accept, to the existing run-launching services
    (code_review_service.launch_run, address_pr_service.launch_run, etc). No
    proposal is created automatically yet (that's the watchers of fase 2) —
    these endpoints exist so accept/dismiss can already be exercised.
    """

    __tablename__ = "proposals"

    __table_args__ = (Index("ix_proposals_status", "status"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # watcher | manual (future: planner)
    source = Column(String, nullable=False)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # start_code_review | start_address_pr | run_skill | run_automation
    action_kind = Column(String, nullable=False)
    # Everything the dispatching service needs to materialize the run.
    action_payload = Column(JSONB, nullable=False)

    # pending | accepted | dismissed | expired
    status = Column(String, nullable=False, default="pending", server_default="pending")
    # Id of the run created when this proposal was accepted.
    result_ref = Column(String, nullable=True)
    # The planner_run that generated this proposal (source="planner"); null for
    # watcher/manual proposals. Lets the UI dismiss a whole day's suggestions.
    plan_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("planner_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
