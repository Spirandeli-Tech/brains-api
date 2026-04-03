import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.bank_account import BankAccount
from app.models.contract import Contract
from app.models.contract_service import ContractService
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.invoice_service import InvoiceService
from app.models.recurring_task import RecurringTask
from app.models.user import User
from app.schemas.contract import ContractCreate, ContractListItem, ContractRead, ContractUpdate

router = APIRouter(prefix="/contracts", tags=["contracts"])


def _sync_recurring_task(db: Session, contract: Contract) -> None:
    """Create or update a RecurringTask linked to this contract."""
    existing = (
        db.query(RecurringTask)
        .filter(
            RecurringTask.reference_id == contract.id,
            RecurringTask.task_type == "generate_contract_invoice",
        )
        .first()
    )

    if contract.status == "active":
        if existing:
            existing.day_of_month = contract.invoice_day
            existing.enabled = True
        else:
            task = RecurringTask(
                user_id=contract.created_by_user_id,
                task_type="generate_contract_invoice",
                reference_id=contract.id,
                frequency="monthly",
                day_of_month=contract.invoice_day,
            )
            db.add(task)
    elif existing:
        existing.enabled = False

    db.commit()


@router.get("", response_model=list[ContractListItem])
def list_contracts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Contract)
        .filter(Contract.created_by_user_id == current_user.id)
        .order_by(Contract.created_at.desc())
    )
    return query.all()


def _generate_invoice_number(db: Session, user_id: UUID) -> str:
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


@router.post("/generate-invoices")
def generate_invoices_for_month(
    year: int = Query(..., description="Year (e.g. 2026)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate invoices for all active contracts for a given month.
    Skips contracts that already have an invoice for that month."""
    import calendar
    max_day = calendar.monthrange(year, month)[1]

    contracts = (
        db.query(Contract)
        .filter(
            Contract.created_by_user_id == current_user.id,
            Contract.status == "active",
        )
        .all()
    )

    generated = []
    skipped = []

    for contract in contracts:
        # Check if invoice already exists for this contract + month
        existing = (
            db.query(Invoice)
            .filter(
                Invoice.contract_id == contract.id,
                extract("year", Invoice.issue_date) == year,
                extract("month", Invoice.issue_date) == month,
            )
            .first()
        )
        if existing:
            skipped.append({"contract_id": str(contract.id), "name": contract.name, "reason": "already_generated"})
            continue

        monthly_value = (contract.annual_value / Decimal(12)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        day = min(contract.invoice_day, max_day)
        issue_date = date(year, month, day)
        due_date = issue_date + timedelta(days=30)

        invoice = Invoice(
            created_by_user_id=current_user.id,
            customer_id=contract.customer_id,
            bank_account_id=contract.bank_account_id,
            invoice_number=_generate_invoice_number(db, current_user.id),
            issue_date=issue_date,
            due_date=due_date,
            currency=contract.currency,
            status="draft",
            total_amount=monthly_value,
            notes=contract.notes,
            contract_id=contract.id,
        )
        db.add(invoice)
        db.flush()

        for svc in contract.services:
            db.add(InvoiceService(
                created_by_user_id=current_user.id,
                invoice_id=invoice.id,
                service_title=svc.service_title,
                service_description=svc.service_description,
                sort_order=svc.sort_order,
            ))

        generated.append({"contract_id": str(contract.id), "name": contract.name, "invoice_id": str(invoice.id)})

    db.commit()

    return {
        "generated": len(generated),
        "skipped": len(skipped),
        "details": {"generated": generated, "skipped": skipped},
    }


@router.get("/{contract_id}", response_model=ContractRead)
def get_contract(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract = (
        db.query(Contract)
        .filter(Contract.id == contract_id, Contract.created_by_user_id == current_user.id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return contract


@router.post("", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
def create_contract(
    data: ContractCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify customer ownership
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

    contract = Contract(
        created_by_user_id=current_user.id,
        customer_id=data.customer_id,
        bank_account_id=data.bank_account_id,
        name=data.name,
        status=data.status,
        annual_value=data.annual_value,
        currency=data.currency,
        invoice_day=data.invoice_day,
        notes=data.notes,
    )
    db.add(contract)
    db.flush()

    for idx, svc in enumerate(data.services):
        service = ContractService(
            created_by_user_id=current_user.id,
            contract_id=contract.id,
            service_title=svc.service_title,
            service_description=svc.service_description,
            amount=svc.amount,
            sort_order=svc.sort_order if svc.sort_order is not None else idx,
        )
        db.add(service)

    db.commit()
    db.refresh(contract)

    _sync_recurring_task(db, contract)

    return contract


@router.put("/{contract_id}", response_model=ContractRead)
def update_contract(
    contract_id: UUID,
    data: ContractUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract = (
        db.query(Contract)
        .filter(Contract.id == contract_id, Contract.created_by_user_id == current_user.id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    if data.customer_id is not None:
        customer = (
            db.query(Customer)
            .filter(Customer.id == data.customer_id, Customer.created_by_user_id == current_user.id)
            .first()
        )
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

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

    for field, value in update_data.items():
        setattr(contract, field, value)

    if services_data is not None:
        db.query(ContractService).filter(ContractService.contract_id == contract.id).delete()
        for idx, svc in enumerate(services_data):
            service = ContractService(
                created_by_user_id=current_user.id,
                contract_id=contract.id,
                service_title=svc["service_title"],
                service_description=svc.get("service_description"),
                amount=svc.get("amount"),
                sort_order=svc.get("sort_order", idx),
            )
            db.add(service)

    db.commit()
    db.refresh(contract)

    # Sync recurring task if status or invoice_day changed
    if data.status is not None or data.invoice_day is not None:
        _sync_recurring_task(db, contract)

    return contract


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contract = (
        db.query(Contract)
        .filter(Contract.id == contract_id, Contract.created_by_user_id == current_user.id)
        .first()
    )
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    # Check if there are invoices linked to this contract
    has_invoices = (
        db.query(Invoice)
        .filter(Invoice.contract_id == contract_id)
        .first()
    )
    if has_invoices:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete contract with linked invoices. Set status to inactive instead.",
        )

    # Delete associated recurring task
    db.query(RecurringTask).filter(
        RecurringTask.reference_id == contract.id,
        RecurringTask.task_type == "generate_contract_invoice",
    ).delete()

    db.delete(contract)
    db.commit()
