import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.bank_account import BankAccount
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.invoice_service import InvoiceService
from app.models.user import User
from app.schemas.invoice import InvoiceCreate, InvoiceListItem, InvoiceRead, InvoiceUpdate

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _generate_invoice_number(db: Session, user_id: UUID) -> str:
    """Generate the next sequential invoice number for a user (INV-000001 format)."""
    latest = (
        db.query(func.max(Invoice.invoice_number))
        .filter(Invoice.created_by_user_id == user_id)
        .scalar()
    )
    if latest:
        match = re.search(r"(\d+)$", latest)
        next_num = int(match.group(1)) + 1 if match else 1
    else:
        next_num = 1
    return f"INV-{next_num:06d}"


@router.get("", response_model=list[InvoiceListItem])
def list_invoices(
    status_filter: str | None = Query(None, alias="status"),
    customer_id: UUID | None = Query(None),
    issue_date_from=Query(None),
    issue_date_to=Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Invoice).filter(Invoice.created_by_user_id == current_user.id)

    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)
    if issue_date_from:
        query = query.filter(Invoice.issue_date >= issue_date_from)
    if issue_date_to:
        query = query.filter(Invoice.issue_date <= issue_date_to)

    query = query.order_by(Invoice.issue_date.desc())
    return query.all()


@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.created_by_user_id == current_user.id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


@router.post("", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(
    data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify customer belongs to the current user
    customer = (
        db.query(Customer)
        .filter(Customer.id == data.customer_id, Customer.created_by_user_id == current_user.id)
        .first()
    )
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # Verify bank account ownership if provided
    if data.bank_account_id is not None:
        bank_account = (
            db.query(BankAccount)
            .filter(BankAccount.id == data.bank_account_id, BankAccount.created_by_user_id == current_user.id)
            .first()
        )
        if not bank_account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    # Compute total from services
    total_amount = sum(s.amount for s in data.services)

    invoice_number = data.invoice_number or _generate_invoice_number(db, current_user.id)

    invoice = Invoice(
        created_by_user_id=current_user.id,
        customer_id=data.customer_id,
        bank_account_id=data.bank_account_id,
        invoice_number=invoice_number,
        issue_date=data.issue_date,
        due_date=data.due_date,
        currency=data.currency,
        status=data.status,
        total_amount=total_amount,
        notes=data.notes,
        is_recurrent=data.is_recurrent,
        recurrence_frequency=data.recurrence_frequency,
        recurrence_day=data.recurrence_day,
    )

    # Retry once if invoice number collides (race condition)
    for attempt in range(2):
        try:
            db.add(invoice)
            db.flush()
            break
        except IntegrityError:
            db.rollback()
            if attempt == 0 and not data.invoice_number:
                invoice.invoice_number = _generate_invoice_number(db, current_user.id)
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Invoice number already exists",
                )

    # Create invoice services
    for idx, svc in enumerate(data.services):
        service = InvoiceService(
            created_by_user_id=current_user.id,
            invoice_id=invoice.id,
            service_title=svc.service_title,
            service_description=svc.service_description,
            amount=svc.amount,
            sort_order=svc.sort_order if svc.sort_order is not None else idx,
        )
        db.add(service)

    db.commit()
    db.refresh(invoice)
    return invoice


@router.put("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: UUID,
    data: InvoiceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.created_by_user_id == current_user.id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    # If changing customer, verify ownership
    if data.customer_id is not None:
        customer = (
            db.query(Customer)
            .filter(Customer.id == data.customer_id, Customer.created_by_user_id == current_user.id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    # If changing bank account, verify ownership
    if data.bank_account_id is not None:
        bank_account = (
            db.query(BankAccount)
            .filter(BankAccount.id == data.bank_account_id, BankAccount.created_by_user_id == current_user.id)
            .first()
        )
        if not bank_account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    update_data = data.model_dump(exclude_unset=True)
    services_data = update_data.pop("services", None)

    # Update scalar fields
    for field, value in update_data.items():
        setattr(invoice, field, value)

    # Replace services if provided
    if services_data is not None:
        # Delete existing services
        db.query(InvoiceService).filter(InvoiceService.invoice_id == invoice.id).delete()

        # Insert new services
        for idx, svc in enumerate(services_data):
            service = InvoiceService(
                created_by_user_id=current_user.id,
                invoice_id=invoice.id,
                service_title=svc["service_title"],
                service_description=svc.get("service_description"),
                amount=svc["amount"],
                sort_order=svc.get("sort_order", idx),
            )
            db.add(service)

        # Recompute total
        invoice.total_amount = sum(s["amount"] for s in services_data)

    db.commit()
    db.refresh(invoice)
    return invoice


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.created_by_user_id == current_user.id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    db.delete(invoice)
    db.commit()
