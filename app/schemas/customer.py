from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CustomerCreate(BaseModel):
    legal_name: str
    display_name: str | None = None
    tax_id: str | None = None
    email: str | None = None
    phone: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None


class CustomerUpdate(BaseModel):
    legal_name: str | None = None
    display_name: str | None = None
    tax_id: str | None = None
    email: str | None = None
    phone: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None


class CustomerRead(BaseModel):
    id: UUID
    legal_name: str
    display_name: str | None
    tax_id: str | None
    email: str | None
    phone: str | None
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state: str | None
    zip: str | None
    country: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
