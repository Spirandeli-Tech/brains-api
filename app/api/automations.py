from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.automations import (
    AutomationCreate,
    AutomationRead,
    AutomationRunClaim,
    AutomationRunRead,
    AutomationRunUpdate,
    AutomationUpdate,
    ClaimAutomationRequest,
    ConnectionInfo,
)
from app.services import automation_service as svc

router = APIRouter(prefix="/automations", tags=["automations"])


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


@router.get("", response_model=list[AutomationRead])
def list_automations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_automations(db, current_user.id)


@router.get("/skills", response_model=list[str])
def list_available_skills(
    current_user: User = Depends(get_current_user),
):
    return svc.list_available_skills()


@router.get("/connections", response_model=list[ConnectionInfo])
def list_available_connections(
    current_user: User = Depends(get_current_user),
):
    """Orgs the runner has registered from its local config.json, with their repos."""
    return svc.list_available_connections()


@router.get("/{automation_id}", response_model=AutomationRead)
def get_automation(
    automation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    automation = svc.get_automation(db, automation_id)
    if not automation or automation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Automation not found")
    return svc._serialize_automation(automation, recent_runs_limit=10_000)


@router.post("", response_model=AutomationRead, status_code=status.HTTP_201_CREATED)
def create_automation(
    data: AutomationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_automation(db, current_user.id, data.model_dump())


@router.patch("/{automation_id}", response_model=AutomationRead)
def update_automation(
    automation_id: UUID,
    data: AutomationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    automation = svc.get_automation(db, automation_id)
    if not automation or automation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Automation not found")
    return svc.update_automation(db, automation, data.model_dump(exclude_unset=True))


@router.post("/{automation_id}/run", response_model=AutomationRunRead, status_code=status.HTTP_201_CREATED)
def run_automation_now(
    automation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    automation = svc.get_automation(db, automation_id)
    if not automation or automation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Automation not found")
    return svc.trigger_manual_run(db, automation)


@router.post("/runs/{run_id}/approve", response_model=AutomationRunRead)
def approve_automation_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a paused (awaiting_approval) automation run — re-enqueues it as
    phase 2 so the runner carries it through its finish phase (e.g. publish)."""
    run = svc.get_automation_run(db, run_id)
    if not run or not run.automation or run.automation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Automation run not found")
    if run.status != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Run is not awaiting approval (status={run.status})",
        )
    return svc.approve_automation_run(db, run)


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(
    automation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    automation = svc.get_automation(db, automation_id)
    if not automation or automation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Automation not found")
    svc.delete_automation(db, automation)


# --- Runner-facing endpoints ---


@router.post("/runner/claim")
def runner_claim_automation(
    data: ClaimAutomationRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    run = svc.claim_next_automation_run(db, data.runner_id)
    if run is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return run


@router.patch("/runner/runs/{run_id}")
def runner_update_automation_run(
    run_id: UUID,
    data: AutomationRunUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    result = svc.update_automation_run(db, run_id, data.model_dump(exclude_unset=True))
    if result is None:
        raise HTTPException(status_code=404, detail="Automation run not found")
    return result
