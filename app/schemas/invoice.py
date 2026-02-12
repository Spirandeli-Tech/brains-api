from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from app.schemas.bank_account import BankAccountRead
from app.schemas.customer import CustomerRead
from app.schemas.invoice_service import InvoiceServiceCreate, InvoiceServiceRead


VALID_STATUSES = ("draft", "sent", "paid", "void")
VALID_FREQUENCIES = ("daily", "weekly", "monthly")


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
    is_recurrent: bool = False
    recurrence_frequency: str | None = None
    recurrence_day: int | None = None

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

    @field_validator("recurrence_frequency")
    @classmethod
    def frequency_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_FREQUENCIES:
            raise ValueError(f"recurrence_frequency must be one of {VALID_FREQUENCIES}")
        return v

    @model_validator(mode="after")
    def due_date_after_issue_date(self) -> "InvoiceCreate":
        if self.due_date < self.issue_date:
            raise ValueError("due_date must be on or after issue_date")
        return self

    @model_validator(mode="after")
    def validate_recurrence(self) -> "InvoiceCreate":
        if self.is_recurrent:
            if not self.recurrence_frequency:
                raise ValueError("recurrence_frequency is required when is_recurrent is true")
            if self.recurrence_frequency == "weekly":
                if self.recurrence_day is None:
                    raise ValueError("recurrence_day is required for weekly recurrence")
                if not (0 <= self.recurrence_day <= 6):
                    raise ValueError("recurrence_day must be between 0 (Monday) and 6 (Sunday) for weekly recurrence")
            elif self.recurrence_frequency == "monthly":
                if self.recurrence_day is None:
                    raise ValueError("recurrence_day is required for monthly recurrence")
                if not (1 <= self.recurrence_day <= 31):
                    raise ValueError("recurrence_day must be between 1 and 31 for monthly recurrence")
            elif self.recurrence_frequency == "daily":
                self.recurrence_day = None
        else:
            self.recurrence_frequency = None
            self.recurrence_day = None
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
    is_recurrent: bool | None = None
    recurrence_frequency: str | None = None
    recurrence_day: int | None = None

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

    @field_validator("recurrence_frequency")
    @classmethod
    def frequency_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_FREQUENCIES:
            raise ValueError(f"recurrence_frequency must be one of {VALID_FREQUENCIES}")
        return v

    @model_validator(mode="after")
    def validate_recurrence(self) -> "InvoiceUpdate":
        if self.is_recurrent is True:
            if not self.recurrence_frequency:
                raise ValueError("recurrence_frequency is required when is_recurrent is true")
            if self.recurrence_frequency == "weekly":
                if self.recurrence_day is None:
                    raise ValueError("recurrence_day is required for weekly recurrence")
                if not (0 <= self.recurrence_day <= 6):
                    raise ValueError("recurrence_day must be between 0 (Monday) and 6 (Sunday) for weekly recurrence")
            elif self.recurrence_frequency == "monthly":
                if self.recurrence_day is None:
                    raise ValueError("recurrence_day is required for monthly recurrence")
                if not (1 <= self.recurrence_day <= 31):
                    raise ValueError("recurrence_day must be between 1 and 31 for monthly recurrence")
            elif self.recurrence_frequency == "daily":
                self.recurrence_day = None
        elif self.is_recurrent is False:
            self.recurrence_frequency = None
            self.recurrence_day = None
        return self


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
    is_recurrent: bool
    recurrence_frequency: str | None
    recurrence_day: int | None
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
    is_recurrent: bool
    recurrence_frequency: str | None

    class Config:
        from_attributes = True
