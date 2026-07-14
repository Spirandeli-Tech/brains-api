from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

VALID_PROPOSAL_STATUSES = ("pending", "accepted", "dismissed", "expired")
VALID_ACTION_KINDS = ("start_code_review", "start_address_pr", "run_skill", "run_automation")


class ProposalRead(BaseModel):
    id: UUID
    created_at: datetime
    source: str
    title: str
    description: str | None
    action_kind: str
    action_payload: dict
    status: str
    result_ref: str | None


class ProposalCreate(BaseModel):
    """Used to seed a proposal manually/for testing — watchers (fase 2) will
    create these automatically once they exist."""

    source: str = "manual"
    title: str
    description: str | None = None
    action_kind: str
    action_payload: dict

    @field_validator("action_kind")
    @classmethod
    def action_kind_valid(cls, v: str) -> str:
        if v not in VALID_ACTION_KINDS:
            raise ValueError(f"Invalid action_kind: {v}")
        return v
