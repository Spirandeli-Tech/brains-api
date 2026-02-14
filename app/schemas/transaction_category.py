from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TransactionCategoryCreate(BaseModel):
    name: str
    color: str | None = None
    icon: str | None = None


class TransactionCategoryUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    icon: str | None = None


class TransactionCategoryRead(BaseModel):
    id: UUID
    name: str
    color: str | None
    icon: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
