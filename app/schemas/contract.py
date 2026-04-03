from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from app.schemas.bank_account import BankAccountRead
from app.schemas.customer import CustomerRead
from app.schemas.invoice_service import InvoiceServiceCreate, InvoiceServiceRead


VALID_STATUSES = ("active", "inactive")


class ContractCreate(BaseModel):
    customer_id: UUID
    name: str
    status: str = "active"
    annual_value: Decimal
    currency: str = "USD"
    invoice_day: int = 1
    bank_account_id: UUID | None = None
    services: list[InvoiceServiceCreate]
    notes: str | None = None
    contract_pdf_url: str | None = None

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

    @field_validator("invoice_day")
    @classmethod
    def invoice_day_must_be_valid(cls, v: int) -> int:
        if not (1 <= v <= 31):
            raise ValueError("invoice_day must be between 1 and 31")
        return v

    @field_validator("annual_value")
    @classmethod
    def annual_value_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("annual_value must be greater than 0")
        return v


class ContractUpdate(BaseModel):
    customer_id: UUID | None = None
    name: str | None = None
    status: str | None = None
    annual_value: Decimal | None = None
    currency: str | None = None
    invoice_day: int | None = None
    bank_account_id: UUID | None = None
    services: list[InvoiceServiceCreate] | None = None
    notes: str | None = None
    contract_pdf_url: str | None = None

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

    @field_validator("invoice_day")
    @classmethod
    def invoice_day_must_be_valid(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 31):
            raise ValueError("invoice_day must be between 1 and 31")
        return v

    @field_validator("annual_value")
    @classmethod
    def annual_value_must_be_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("annual_value must be greater than 0")
        return v


class ContractRead(BaseModel):
    id: UUID
    name: str
    customer: CustomerRead
    bank_account: BankAccountRead | None
    status: str
    annual_value: Decimal
    currency: str
    invoice_day: int
    services: list[InvoiceServiceRead]
    notes: str | None
    contract_pdf_url: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContractListItem(BaseModel):
    id: UUID
    name: str
    customer: CustomerRead
    status: str
    annual_value: Decimal
    currency: str
    invoice_day: int
    created_at: datetime

    class Config:
        from_attributes = True
