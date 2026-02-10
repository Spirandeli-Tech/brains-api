from uuid import UUID
from pydantic import BaseModel
from datetime import datetime


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
    last_login: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
