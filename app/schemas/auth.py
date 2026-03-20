from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from app.schemas.user import RoleResponse


class RegisterRequest(BaseModel):
    firebase_token: str
    first_name: str
    last_name: str


class LoginRequest(BaseModel):
    firebase_token: str


class UserResponse(BaseModel):
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
