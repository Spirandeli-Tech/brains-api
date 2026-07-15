from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.user import User
from app.schemas.watchers import (
    ClaimWatcherRequest,
    WatcherClaimRead,
    WatcherCreate,
    WatcherRead,
    WatcherReport,
    WatcherUpdate,
)
from app.services import watcher_service as svc

router = APIRouter(prefix="/watchers", tags=["watchers"])


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


@router.get("", response_model=list[WatcherRead])
def list_watchers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_watchers(db, current_user.id)


@router.post("", response_model=WatcherRead, status_code=status.HTTP_201_CREATED)
def create_watcher(
    data: WatcherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_watcher(db, current_user.id, data.model_dump())


@router.patch("/{watcher_id}", response_model=WatcherRead)
def update_watcher(
    watcher_id: UUID,
    data: WatcherUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    watcher = svc.get_watcher(db, watcher_id)
    if not watcher or watcher.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return svc.update_watcher(db, watcher, data.model_dump(exclude_unset=True))


@router.delete("/{watcher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watcher(
    watcher_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    watcher = svc.get_watcher(db, watcher_id)
    if not watcher or watcher.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Watcher not found")
    svc.delete_watcher(db, watcher)


# --- Runner-facing endpoints ---


@router.post("/runner/claim", response_model=WatcherClaimRead | None)
def runner_claim_watcher(
    data: ClaimWatcherRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    watcher = svc.claim_next_watcher(db, data.runner_id)
    if watcher is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return watcher


@router.patch("/runner/{watcher_id}/report")
def runner_report_watcher(
    watcher_id: UUID,
    data: WatcherReport,
    db: Session = Depends(get_db),
    _: bool = Depends(require_runner),
):
    result = svc.report_watcher_tick(
        db,
        watcher_id,
        [s.model_dump() for s in data.sightings],
        data.status,
        data.error,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return result
