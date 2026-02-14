from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.db import get_db
from app.models.transaction import Transaction
from app.models.transaction_category import TransactionCategory
from app.models.user import User
from app.schemas.transaction_category import (
    TransactionCategoryCreate,
    TransactionCategoryRead,
    TransactionCategoryUpdate,
)

router = APIRouter(prefix="/transaction-categories", tags=["transaction-categories"])


@router.get("", response_model=list[TransactionCategoryRead])
def list_transaction_categories(
    q: str | None = Query(None, description="Search by category name"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(TransactionCategory).filter(
        TransactionCategory.created_by_user_id == current_user.id
    )
    if q:
        query = query.filter(TransactionCategory.name.ilike(f"%{q}%"))
    return query.order_by(TransactionCategory.name).all()


@router.get("/{category_id}", response_model=TransactionCategoryRead)
def get_transaction_category(
    category_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = (
        db.query(TransactionCategory)
        .filter(
            TransactionCategory.id == category_id,
            TransactionCategory.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )
    return category


@router.post(
    "", response_model=TransactionCategoryRead, status_code=status.HTTP_201_CREATED
)
def create_transaction_category(
    data: TransactionCategoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(TransactionCategory)
        .filter(
            TransactionCategory.created_by_user_id == current_user.id,
            TransactionCategory.name == data.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A category with this name already exists",
        )
    category = TransactionCategory(
        created_by_user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.put("/{category_id}", response_model=TransactionCategoryRead)
def update_transaction_category(
    category_id: UUID,
    data: TransactionCategoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = (
        db.query(TransactionCategory)
        .filter(
            TransactionCategory.id == category_id,
            TransactionCategory.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction_category(
    category_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = (
        db.query(TransactionCategory)
        .filter(
            TransactionCategory.id == category_id,
            TransactionCategory.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )

    has_transactions = (
        db.query(Transaction)
        .filter(Transaction.category_id == category_id)
        .first()
    )
    if has_transactions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category is used by transactions and cannot be deleted",
        )

    db.delete(category)
    db.commit()
