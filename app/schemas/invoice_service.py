from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, field_validator


class InvoiceServiceCreate(BaseModel):
    service_title: str
    service_description: str | None = None
    amount: Decimal
    sort_order: int | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be greater than 0")
        return v


class InvoiceServiceRead(BaseModel):
    id: UUID
    service_title: str
    service_description: str | None
    amount: Decimal
    sort_order: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
