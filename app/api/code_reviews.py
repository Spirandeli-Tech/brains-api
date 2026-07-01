import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.code_reviews import (
    ApproveRequest,
    ClaimRequest,
    IterateRequest,
    LaunchReviewRequest,
    RunRead,
    RunUpdate,
    StepUpdate,
)
from app.services import code_review_service as svc

# Reuse the runner-auth guard from implementations to avoid duplicating the
# RUNNER_TOKEN logic.
from app.api.implementations import require_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/code-reviews", tags=["code-reviews"])


# --- User-facing endpoints (control plane / UI) ---


@router.get("/runs", response_model=list[RunRead])
def list_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runs = svc.list_runs(db, current_user.id)
    return [svc.to_run_read(r) for r in runs]


@router.post("/runs", response_model=RunRead, status_code=status.HTTP_201_CREATED)
def launch_run(
    data: LaunchReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = svc.launch_run(
        db,
        user_id=current_user.id,
        connection_id=data.connection_id,
        pr_url=data.pr_url,
        repo_name=data.repo_name,
        ticket_key=data.ticket_key,
        instructions=data.instructions,
    )
    return svc.to_run_read(run)


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = svc.get_run(db, run_id)
    if not run or run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return svc.to_run_read(run)


@router.post("/runs/{run_id}/steps/{step_id}/approve", response_model=RunRead)
def approve_step(
    run_id: UUID,
    step_id: UUID,
    data: ApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = svc.get_run(db, run_id)
    if not run or run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        run = svc.approve_step(db, run, step_id, data.review_action, data.review_plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.to_run_read(run)


@router.post("/runs/{run_id}/steps/{step_id}/iterate", response_model=RunRead)
def iterate_step(
    run_id: UUID,
    step_id: UUID,
    data: IterateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = svc.get_run(db, run_id)
    if not run or run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        run = svc.iterate_step(db, run, step_id, data.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.to_run_read(run)


@router.post("/runs/{run_id}/restart", response_model=RunRead)
def restart_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = svc.get_run(db, run_id)
    if not run or run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status == "done":
        raise HTTPException(status_code=400, detail="Cannot restart a completed run")
    return svc.to_run_read(svc.restart_run(db, run))


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = svc.get_run(db, run_id)
    if not run or run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    svc.cancel_run(db, run)


# --- Runner-facing endpoints (execution plane) ---


@router.post("/runner/claim", response_model=RunRead | None)
def runner_claim(
    data: ClaimRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    run = svc.claim_next_run(db, data.runner_id)
    return svc.to_run_read(run) if run else None


@router.patch("/runner/runs/{run_id}", response_model=RunRead)
def runner_update_run(
    run_id: UUID,
    data: RunUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    run = svc.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run = svc.update_run(db, run, data.model_dump(exclude_unset=True))
    return svc.to_run_read(run)


@router.patch("/runner/runs/{run_id}/steps/{step_id}", response_model=RunRead)
def runner_update_step(
    run_id: UUID,
    step_id: UUID,
    data: StepUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    run = svc.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        run = svc.update_step(db, run, step_id, data.status, data.log)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.to_run_read(run)
