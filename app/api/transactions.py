from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.bank_account import BankAccount
from app.models.transaction import Transaction
from app.models.transaction_category import TransactionCategory
from app.models.user import User
from app.schemas.transaction import (
    BankAccountBalance,
    TransactionCreate,
    TransactionListItem,
    TransactionRead,
    TransactionSummary,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _apply_filters(
    query,
    current_user_id,
    type_filter,
    context_filter,
    category_id,
    bank_account_id,
    date_from,
    date_to,
):
    query = query.filter(Transaction.created_by_user_id == current_user_id)
    if type_filter:
        query = query.filter(Transaction.type == type_filter)
    if context_filter:
        query = query.filter(Transaction.context == context_filter)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if bank_account_id:
        query = query.filter(Transaction.bank_account_id == bank_account_id)
    if date_from:
        query = query.filter(Transaction.date >= date_from)
    if date_to:
        query = query.filter(Transaction.date <= date_to)
    return query


@router.get("", response_model=list[TransactionListItem])
def list_transactions(
    type_filter: str | None = Query(None, alias="type"),
    context_filter: str | None = Query(None, alias="context"),
    category_id: UUID | None = Query(None),
    bank_account_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = _apply_filters(
        db.query(Transaction),
        current_user.id,
        type_filter,
        context_filter,
        category_id,
        bank_account_id,
        date_from,
        date_to,
    )
    return query.order_by(Transaction.date.desc(), Transaction.created_at.desc()).all()


@router.get("/summary", response_model=TransactionSummary)
def get_transaction_summary(
    type_filter: str | None = Query(None, alias="type"),
    context_filter: str | None = Query(None, alias="context"),
    category_id: UUID | None = Query(None),
    bank_account_id: UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base_query = _apply_filters(
        db.query(Transaction),
        current_user.id,
        type_filter,
        context_filter,
        category_id,
        bank_account_id,
        date_from,
        date_to,
    )
    result = base_query.with_entities(
        func.coalesce(
            func.sum(
                case((Transaction.type == "income", Transaction.amount), else_=0)
            ),
            0,
        ).label("total_income"),
        func.coalesce(
            func.sum(
                case((Transaction.type == "expense", Transaction.amount), else_=0)
            ),
            0,
        ).label("total_expenses"),
        func.count(Transaction.id).label("transaction_count"),
    ).first()

    total_income = Decimal(str(result.total_income))
    total_expenses = Decimal(str(result.total_expenses))

    return TransactionSummary(
        total_income=total_income,
        total_expenses=total_expenses,
        net_balance=total_income - total_expenses,
        transaction_count=result.transaction_count,
    )


@router.get("/bank-balances", response_model=list[BankAccountBalance])
def get_bank_account_balances(
    context_filter: str | None = Query(None, alias="context"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(
            Transaction.bank_account_id,
            BankAccount.label.label("bank_account_label"),
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.type == "income", Transaction.amount), else_=0
                    )
                ),
                0,
            ).label("total_income"),
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.type == "expense", Transaction.amount), else_=0
                    )
                ),
                0,
            ).label("total_expenses"),
        )
        .join(BankAccount, Transaction.bank_account_id == BankAccount.id)
        .filter(Transaction.created_by_user_id == current_user.id)
    )
    if context_filter:
        query = query.filter(Transaction.context == context_filter)

    results = query.group_by(
        Transaction.bank_account_id, BankAccount.label
    ).all()

    return [
        BankAccountBalance(
            bank_account_id=row.bank_account_id,
            bank_account_label=row.bank_account_label,
            total_income=Decimal(str(row.total_income)),
            total_expenses=Decimal(str(row.total_expenses)),
            balance=Decimal(str(row.total_income)) - Decimal(str(row.total_expenses)),
        )
        for row in results
    ]


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = (
        db.query(Transaction)
        .filter(
            Transaction.id == transaction_id,
            Transaction.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )
    return transaction


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    data: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.category_id is not None:
        category = (
            db.query(TransactionCategory)
            .filter(
                TransactionCategory.id == data.category_id,
                TransactionCategory.created_by_user_id == current_user.id,
            )
            .first()
        )
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )

    if data.bank_account_id is not None:
        bank_account = (
            db.query(BankAccount)
            .filter(
                BankAccount.id == data.bank_account_id,
                BankAccount.created_by_user_id == current_user.id,
            )
            .first()
        )
        if not bank_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bank account not found",
            )

    transaction = Transaction(
        created_by_user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


@router.put("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: UUID,
    data: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = (
        db.query(Transaction)
        .filter(
            Transaction.id == transaction_id,
            Transaction.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )

    update_data = data.model_dump(exclude_unset=True)

    if "category_id" in update_data and update_data["category_id"] is not None:
        category = (
            db.query(TransactionCategory)
            .filter(
                TransactionCategory.id == update_data["category_id"],
                TransactionCategory.created_by_user_id == current_user.id,
            )
            .first()
        )
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )

    if "bank_account_id" in update_data and update_data["bank_account_id"] is not None:
        bank_account = (
            db.query(BankAccount)
            .filter(
                BankAccount.id == update_data["bank_account_id"],
                BankAccount.created_by_user_id == current_user.id,
            )
            .first()
        )
        if not bank_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bank account not found",
            )

    for field, value in update_data.items():
        setattr(transaction, field, value)

    db.commit()
    db.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = (
        db.query(Transaction)
        .filter(
            Transaction.id == transaction_id,
            Transaction.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )

    db.delete(transaction)
    db.commit()
