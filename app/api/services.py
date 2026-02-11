from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.invoice_service import InvoiceService
from app.models.user import User
from app.schemas.invoice_service import InvoiceServiceCreate, InvoiceServiceRead, InvoiceServiceUpdate

router = APIRouter(prefix="/services", tags=["services"])


@router.get("", response_model=list[InvoiceServiceRead])
def list_services(
    q: str | None = Query(None, description="Search by service title"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(InvoiceService).filter(
        InvoiceService.created_by_user_id == current_user.id,
        InvoiceService.invoice_id.is_(None),
    )
    if q:
        query = query.filter(InvoiceService.service_title.ilike(f"%{q}%"))
    query = query.order_by(InvoiceService.service_title)
    return query.all()


@router.get("/{service_id}", response_model=InvoiceServiceRead)
def get_service(
    service_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = (
        db.query(InvoiceService)
        .filter(
            InvoiceService.id == service_id,
            InvoiceService.created_by_user_id == current_user.id,
            InvoiceService.invoice_id.is_(None),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


@router.post("", response_model=InvoiceServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    data: InvoiceServiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = InvoiceService(
        created_by_user_id=current_user.id,
        invoice_id=None,
        service_title=data.service_title,
        service_description=data.service_description,
        amount=data.amount,
        sort_order=data.sort_order,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.put("/{service_id}", response_model=InvoiceServiceRead)
def update_service(
    service_id: UUID,
    data: InvoiceServiceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = (
        db.query(InvoiceService)
        .filter(
            InvoiceService.id == service_id,
            InvoiceService.created_by_user_id == current_user.id,
            InvoiceService.invoice_id.is_(None),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    service_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = (
        db.query(InvoiceService)
        .filter(
            InvoiceService.id == service_id,
            InvoiceService.created_by_user_id == current_user.id,
            InvoiceService.invoice_id.is_(None),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    db.delete(service)
    db.commit()
