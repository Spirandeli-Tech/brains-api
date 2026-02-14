import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.schemas.bank_account import BankAccountRead
from app.schemas.transaction_category import TransactionCategoryRead


VALID_TYPES = ("expense", "income")
VALID_CONTEXTS = ("business", "personal")


class TransactionCreate(BaseModel):
    type: str
    context: str = "business"
    description: str
    amount: Decimal
    currency: str = "USD"
    date: datetime.date
    category_id: UUID | None = None
    bank_account_id: UUID | None = None
    notes: str | None = None

    @field_validator("type")
    @classmethod
    def type_must_be_valid(cls, v: str) -> str:
        if v not in VALID_TYPES:
            raise ValueError(f"type must be one of {VALID_TYPES}")
        return v

    @field_validator("context")
    @classmethod
    def context_must_be_valid(cls, v: str) -> str:
        if v not in VALID_CONTEXTS:
            raise ValueError(f"context must be one of {VALID_CONTEXTS}")
        return v

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_three_letters(cls, v: str) -> str:
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter code")
        return v.upper()


class TransactionUpdate(BaseModel):
    type: str | None = None
    context: str | None = None
    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    date: datetime.date | None = None
    category_id: UUID | None = None
    bank_account_id: UUID | None = None
    notes: str | None = None

    @field_validator("type")
    @classmethod
    def type_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TYPES:
            raise ValueError(f"type must be one of {VALID_TYPES}")
        return v

    @field_validator("context")
    @classmethod
    def context_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CONTEXTS:
            raise ValueError(f"context must be one of {VALID_CONTEXTS}")
        return v

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("amount must be greater than 0")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_three_letters(cls, v: str | None) -> str | None:
        if v is not None:
            if len(v) != 3 or not v.isalpha():
                raise ValueError("currency must be a 3-letter code")
            return v.upper()
        return v


class TransactionRead(BaseModel):
    id: UUID
    type: str
    context: str
    description: str
    amount: Decimal
    currency: str
    date: datetime.date
    category: TransactionCategoryRead | None
    bank_account: BankAccountRead | None
    notes: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class TransactionListItem(BaseModel):
    id: UUID
    type: str
    context: str
    description: str
    amount: Decimal
    currency: str
    date: datetime.date
    category: TransactionCategoryRead | None
    bank_account: BankAccountRead | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class TransactionSummary(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    transaction_count: int


class BankAccountBalance(BaseModel):
    bank_account_id: UUID
    bank_account_label: str
    total_income: Decimal
    total_expenses: Decimal
    balance: Decimal
