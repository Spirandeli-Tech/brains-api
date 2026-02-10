from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.bank_account import BankAccount
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.bank_account import BankAccountCreate, BankAccountRead, BankAccountUpdate

router = APIRouter(prefix="/bank-accounts", tags=["bank-accounts"])


@router.get("", response_model=list[BankAccountRead])
def list_bank_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(BankAccount)
        .filter(BankAccount.created_by_user_id == current_user.id)
        .order_by(BankAccount.label)
        .all()
    )


@router.get("/{bank_account_id}", response_model=BankAccountRead)
def get_bank_account(
    bank_account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(BankAccount)
        .filter(BankAccount.id == bank_account_id, BankAccount.created_by_user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    return account


@router.post("", response_model=BankAccountRead, status_code=status.HTTP_201_CREATED)
def create_bank_account(
    data: BankAccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = BankAccount(
        created_by_user_id=current_user.id,
        **data.model_dump(),
    )
    try:
        db.add(account)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A bank account with this label already exists",
        )
    db.commit()
    db.refresh(account)
    return account


@router.put("/{bank_account_id}", response_model=BankAccountRead)
def update_bank_account(
    bank_account_id: UUID,
    data: BankAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(BankAccount)
        .filter(BankAccount.id == bank_account_id, BankAccount.created_by_user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(account, field, value)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A bank account with this label already exists",
        )
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{bank_account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_account(
    bank_account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(BankAccount)
        .filter(BankAccount.id == bank_account_id, BankAccount.created_by_user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")

    # Block deletion if referenced by invoices
    invoice_count = (
        db.query(Invoice)
        .filter(Invoice.bank_account_id == bank_account_id, Invoice.created_by_user_id == current_user.id)
        .count()
    )
    if invoice_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete bank account that is referenced by invoices",
        )

    db.delete(account)
    db.commit()
