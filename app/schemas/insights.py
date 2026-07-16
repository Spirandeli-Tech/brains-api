from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.proposals import ProposalRead


class PlannerRunRead(BaseModel):
    id: UUID
    plan_date: date
    status: str
    narrative: str | None
    highlights: list[dict] | None
    board_summary: dict | None
    claude_cost_usd: float | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class InsightsRead(BaseModel):
    date: date
    run: PlannerRunRead | None
    proposals: list[ProposalRead]


# --- Runner-facing ---


class ClaimPlannerRequest(BaseModel):
    runner_id: str


class PlannerClaimRead(BaseModel):
    id: UUID
    plan_date: date


class PlannerSuggestion(BaseModel):
    title: str
    description: str | None = None
    action_kind: str
    action_payload: dict = {}


class PlannerHighlight(BaseModel):
    org: str | None = None
    text: str
    tone: str = "info"  # urgent | warning | info


class PlannerReport(BaseModel):
    status: str = "done"  # "done" | "failed"
    narrative: str | None = None
    highlights: list[PlannerHighlight] = []
    board_summary: dict | None = None
    suggestions: list[PlannerSuggestion] = []
    claude_cost_usd: float | None = None
    error: str | None = None
