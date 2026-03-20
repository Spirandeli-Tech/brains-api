from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class UserPreferencesUpdate(BaseModel):
    report_theme_color: str | None = None
    report_header_image_url: str | None = None
    default_currency: str | None = None


class UserPreferencesRead(BaseModel):
    id: UUID
    user_id: UUID
    report_theme_color: str | None
    report_header_image_url: str | None
    default_currency: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

