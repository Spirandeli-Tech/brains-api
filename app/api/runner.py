from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.runner import HeartbeatIn, RunnerOverview
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


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(
    payload: HeartbeatIn,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    svc.record_heartbeat(db, payload.model_dump())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/overview", response_model=RunnerOverview)
def overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.build_overview(db)
