from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.proposals import ProposalCreate, ProposalRead
from app.services import proposals_service as svc

router = APIRouter(prefix="/proposals", tags=["proposals"])


@router.get("", response_model=list[ProposalRead])
def list_proposals(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.list_proposals(db, status_filter)


@router.post("", response_model=ProposalRead, status_code=status.HTTP_201_CREATED)
def create_proposal(
    data: ProposalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.create_proposal(db, data.model_dump())


@router.post("/{proposal_id}/accept", response_model=ProposalRead)
def accept_proposal(
    proposal_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = svc.get_proposal(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    try:
        return svc.accept_proposal(db, proposal, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{proposal_id}/dismiss", response_model=ProposalRead)
def dismiss_proposal(
    proposal_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = svc.get_proposal(db, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    try:
        return svc.dismiss_proposal(db, proposal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
