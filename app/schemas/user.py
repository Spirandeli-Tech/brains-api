from uuid import UUID
from pydantic import BaseModel
from datetime import datetime


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str | None

    class Config:
        from_attributes = True


class UserWithRoleResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    firebase_id: str
    last_login: datetime | None
    created_at: datetime
    role: RoleResponse | None

    class Config:
        from_attributes = True
