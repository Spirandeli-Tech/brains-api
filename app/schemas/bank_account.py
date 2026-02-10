from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BankAccountCreate(BaseModel):
    label: str
    beneficiary_full_name: str
    beneficiary_full_address: str | None = None
    beneficiary_account_number: str
    swift_code: str
    bank_name: str | None = None
    bank_address: str | None = None
    intermediary_bank_info: str | None = None


class BankAccountUpdate(BaseModel):
    label: str | None = None
    beneficiary_full_name: str | None = None
    beneficiary_full_address: str | None = None
    beneficiary_account_number: str | None = None
    swift_code: str | None = None
    bank_name: str | None = None
    bank_address: str | None = None
    intermediary_bank_info: str | None = None


class BankAccountRead(BaseModel):
    id: UUID
    label: str
    beneficiary_full_name: str
    beneficiary_full_address: str | None
    beneficiary_account_number: str
    swift_code: str
    bank_name: str | None
    bank_address: str | None
    intermediary_bank_info: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
