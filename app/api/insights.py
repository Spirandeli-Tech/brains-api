from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.insights import (
    ClaimPlannerRequest,
    InsightsRead,
    PlannerClaimRead,
    PlannerReport,
)
from app.services import planner_service as svc

router = APIRouter(prefix="/insights", tags=["insights"])


def require_runner(x_runner_token: str | None = Header(default=None)) -> bool:
    if not settings.RUNNER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runner endpoints are disabled. Set RUNNER_TOKEN to enable.",
        )
    if x_runner_token != settings.RUNNER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid runner token",
        )
    return True


# --- User-facing endpoints ---


@router.get("", response_model=InsightsRead)
def get_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Today's plan. Creates the run on read if it doesn't exist yet (the
    lazy/catch-up trigger for when the Mac was off at the scheduled hour)."""
    return svc.build_insights(db, current_user.id)


@router.get("/{plan_date}", response_model=InsightsRead)
def get_insights_for_date(
    plan_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.build_insights(db, current_user.id, plan_date)


# --- Runner-facing endpoints ---


@router.post("/runner/claim", response_model=PlannerClaimRead | None)
def runner_claim_planner(
    data: ClaimPlannerRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    run = svc.claim_next_planner(db, data.runner_id)
    if run is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return run


@router.patch("/runner/runs/{run_id}")
def runner_report_planner(
    run_id: UUID,
    data: PlannerReport,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    if data.status == "failed":
        result = svc.report_planner_error(db, run_id, data.error or "unknown error")
    else:
        result = svc.report_planner(
            db,
            run_id,
            narrative=data.narrative,
            highlights=[h.model_dump() for h in data.highlights],
            board_summary=data.board_summary,
            suggestions=[s.model_dump() for s in data.suggestions],
            claude_cost_usd=data.claude_cost_usd,
        )
    if result is None:
        raise HTTPException(status_code=404, detail="Planner run not found")
    return result
