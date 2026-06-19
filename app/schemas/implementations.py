from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

VALID_STEP_KINDS = (
    "move_to_progress",
    "research",
    "implement",
    "open_pr",
    "code_review",
    "address_feedback",
    "qa_notes",
    "move_card",
)

VALID_RUN_STATUSES = (
    "queued",
    "running",
    "awaiting_approval",
    "done",
    "failed",
    "cancelled",
)

VALID_STEP_STATUSES = (
    "pending",
    "running",
    "awaiting_approval",
    "done",
    "failed",
    "skipped",
)


# --- User-facing ---


class LaunchRunRequest(BaseModel):
    connection_id: UUID
    ticket_url: str
    steps: list[str]
    instructions: str | None = None

    @field_validator("steps")
    @classmethod
    def steps_must_be_valid(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one step must be selected")
        for kind in v:
            if kind not in VALID_STEP_KINDS:
                raise ValueError(f"Invalid step kind: {kind}")
        return v

    @field_validator("ticket_url")
    @classmethod
    def ticket_url_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ticket_url is required")
        return v.strip()


class StepRead(BaseModel):
    id: UUID
    kind: str
    sensitive: bool
    status: str
    approved: bool
    log: str | None
    started_at: datetime | None
    ended_at: datetime | None

    class Config:
        from_attributes = True


class RunRead(BaseModel):
    id: UUID
    connection_id: UUID | None
    connection_name: str
    provider: str
    ticket_url: str
    ticket_key: str | None
    ticket_summary: str | None
    instructions: str | None
    status: str
    worktree_path: str | None
    branch: str | None
    pr_url: str | None
    error: str | None
    steps: list[StepRead]
    created_at: datetime
    updated_at: datetime


# --- Runner-facing (host execution plane) ---


class StepUpdate(BaseModel):
    """Partial update the runner pushes for a single step."""

    status: str | None = None
    log: str | None = None

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STEP_STATUSES:
            raise ValueError(f"Invalid step status: {v}")
        return v


class RunUpdate(BaseModel):
    """Partial update the runner pushes for the run as a whole."""

    status: str | None = None
    worktree_path: str | None = None
    branch: str | None = None
    pr_url: str | None = None
    error: str | None = None

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_RUN_STATUSES:
            raise ValueError(f"Invalid run status: {v}")
        return v


class DiscussRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def message_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message is required")
        return v.strip()


class ClaimRequest(BaseModel):
    runner_id: str
