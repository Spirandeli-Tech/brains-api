from uuid import UUID
from pydantic import BaseModel
from datetime import datetime


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str | None

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    photo_url: str | None = None


class UserWithRoleResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    firebase_id: str
    photo_url: str | None = None
    last_login: datetime | None
    created_at: datetime
    role: RoleResponse | None

    class Config:
        from_attributes = True
