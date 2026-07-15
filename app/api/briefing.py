from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.briefing import BriefingRead, EventRead
from app.services import platform_events_service as svc

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("", response_model=BriefingRead)
def get_briefing(
    target_date: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.build_briefing(db, target_date or date.today())


@router.get("/events", response_model=list[EventRead])
def list_recent_events(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_recent_events(db, limit)


@router.post("/seen", status_code=204)
def mark_seen(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc.mark_all_seen(db)
