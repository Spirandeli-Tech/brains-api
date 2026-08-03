from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.runner import HeartbeatIn, HeartbeatOut, RestartOut, RunnerOverview
from app.services import address_pr_service
from app.services import automation_service
from app.services import code_review_service
from app.services import implementation_service
from app.services import runner_service as svc

router = APIRouter(prefix="/runner", tags=["runner"])


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


@router.post("/heartbeat", response_model=HeartbeatOut)
def heartbeat(
    payload: HeartbeatIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    return svc.record_heartbeat(db, payload.model_dump())


@router.get("/overview", response_model=RunnerOverview)
def overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.build_overview(db)


@router.post("/{runner_id}/restart", response_model=RestartOut)
def restart_runner(
    runner_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ask a runner to bounce itself.

    We can't reach the runner process directly — it lives on Lucas's laptop, not
    in this container — so the request is parked on its heartbeat row and picked
    up on the next ping (within a few seconds). The runner then kills whatever it
    was running and exits; its start.sh wrapper brings it straight back up.
    """
    result = svc.request_restart(db, runner_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Runner not found")
    return result


_ALREADY_RUNNING = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="O runner já pegou esse job — não dá pra cancelar em execução.",
)


@router.post("/queue/{kind}/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_queued_run(
    kind: str,
    run_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drop a queued job off the runner's queue, whichever table it lives in.

    Only jobs the runner hasn't claimed yet: aborting work already in flight
    would need the runner's cooperation, which it doesn't have today.
    """
    if kind == "automation":
        run = automation_service.get_automation_run(db, run_id)
        if not run or not run.automation or run.automation.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Run not found")
        if not automation_service.cancel_automation_run(db, run):
            raise _ALREADY_RUNNING
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    services = {
        "implementation": implementation_service,
        "code_review": code_review_service,
        "address_pr": address_pr_service,
    }
    service = services.get(kind)
    if service is None:
        raise HTTPException(status_code=400, detail=f"Kind '{kind}' cannot be cancelled")

    run = service.get_run(db, run_id)
    if not run or run.created_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status == "running":
        raise _ALREADY_RUNNING
    service.cancel_run(db, run)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
