from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserWithRoleResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserWithRoleResponse])
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all users with their roles. Requires authentication."""
    users = db.query(User).all()
    return users
