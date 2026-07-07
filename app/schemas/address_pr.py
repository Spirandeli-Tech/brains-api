from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

VALID_STEP_KINDS = ("fix_draft", "commit_push", "post_replies")

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

# Steps that pause for human approval after they run, instead of running straight through.
APPROVABLE_STEP_KINDS = ("fix_draft", "commit_push")


# --- User-facing ---


class LaunchAddressPrRequest(BaseModel):
    connection_id: UUID
    pr_url: str
    repo_name: str | None = None
    ticket_key: str | None = None
    instructions: str | None = None

    @field_validator("pr_url")
    @classmethod
    def pr_url_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("pr_url is required")
        return v.strip()


class ApproveRequest(BaseModel):
    """Payload the UI sends when approving fix_draft or commit_push.

    `fix_plan` is the full items list, with `apply_fix`/`post_reply` flags
    (and edited `reply` text) reflecting the user's checkboxes for whichever
    gate is being approved.
    """
    fix_plan: dict | None = None


class IterateRequest(BaseModel):
    notes: str

    @field_validator("notes")
    @classmethod
    def notes_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("notes is required")
        return v.strip()


class ClaimRequest(BaseModel):
    runner_id: str


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
    pr_url: str
    pr_number: str | None
    repo_name: str | None
    ticket_key: str | None
    instructions: str | None
    status: str
    worktree_path: str | None
    branch: str | None
    fix_plan: dict | None
    error: str | None
    steps: list[StepRead]
    created_at: datetime
    updated_at: datetime


# --- Runner-facing (host execution plane) ---


class StepUpdate(BaseModel):
    status: str | None = None
    log: str | None = None

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STEP_STATUSES:
            raise ValueError(f"Invalid step status: {v}")
        return v


class RunUpdate(BaseModel):
    status: str | None = None
    pr_number: str | None = None
    worktree_path: str | None = None
    branch: str | None = None
    fix_plan: dict | None = None
    error: str | None = None

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_RUN_STATUSES:
            raise ValueError(f"Invalid run status: {v}")
        return v
