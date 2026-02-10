from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from app.schemas.bank_account import BankAccountRead
from app.schemas.customer import CustomerRead
from app.schemas.invoice_service import InvoiceServiceCreate, InvoiceServiceRead


VALID_STATUSES = ("draft", "sent", "paid", "void")


class InvoiceCreate(BaseModel):
    customer_id: UUID
    invoice_number: str | None = None
    issue_date: date
    due_date: date
    currency: str = "USD"
    status: str = "draft"
    bank_account_id: UUID | None = None
    services: list[InvoiceServiceCreate]
    notes: str | None = None

    @field_validator("services")
    @classmethod
    def services_must_not_be_empty(cls, v: list[InvoiceServiceCreate]) -> list[InvoiceServiceCreate]:
        if len(v) < 1:
            raise ValueError("At least one service is required")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_three_letters(cls, v: str) -> str:
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter code")
        return v.upper()

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v

    @model_validator(mode="after")
    def due_date_after_issue_date(self) -> "InvoiceCreate":
        if self.due_date < self.issue_date:
            raise ValueError("due_date must be on or after issue_date")
        return self


class InvoiceUpdate(BaseModel):
    customer_id: UUID | None = None
    invoice_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    status: str | None = None
    bank_account_id: UUID | None = None
    services: list[InvoiceServiceCreate] | None = None
    notes: str | None = None

    @field_validator("services")
    @classmethod
    def services_must_not_be_empty(cls, v: list[InvoiceServiceCreate] | None) -> list[InvoiceServiceCreate] | None:
        if v is not None and len(v) < 1:
            raise ValueError("At least one service is required")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_three_letters(cls, v: str | None) -> str | None:
        if v is not None:
            if len(v) != 3 or not v.isalpha():
                raise ValueError("currency must be a 3-letter code")
            return v.upper()
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}")
        return v


class InvoiceRead(BaseModel):
    id: UUID
    invoice_number: str
    customer: CustomerRead
    bank_account: BankAccountRead | None
    issue_date: date
    due_date: date
    currency: str
    status: str
    total_amount: Decimal
    services: list[InvoiceServiceRead]
    notes: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InvoiceListItem(BaseModel):
    id: UUID
    invoice_number: str
    customer: CustomerRead
    issue_date: date
    due_date: date
    status: str
    total_amount: Decimal
    currency: str

    class Config:
        from_attributes = True
