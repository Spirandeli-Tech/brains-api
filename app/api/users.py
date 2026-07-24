from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.schemas.user import UserWithRoleResponse, UserUpdateRequest
from app.schemas.user_preferences import UserPreferencesRead, UserPreferencesUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserWithRoleResponse])
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active users with their roles. Requires authentication."""
    users = db.query(User).filter(User.deleted_at.is_(None)).all()
    return users


@router.get("/me", response_model=UserWithRoleResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Get the authenticated user's profile."""
    return current_user


@router.put("/me", response_model=UserWithRoleResponse)
def update_current_user_profile(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the authenticated user's profile (first_name, last_name, photo_url)."""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/preferences", response_model=UserPreferencesRead)
def get_user_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the authenticated user's preferences. Creates defaults if none exist."""
    prefs = (
        db.query(UserPreferences)
        .filter(UserPreferences.user_id == current_user.id)
        .first()
    )
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


@router.put("/me/preferences", response_model=UserPreferencesRead)
def update_user_preferences(
    data: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the authenticated user's preferences."""
    prefs = (
        db.query(UserPreferences)
        .filter(UserPreferences.user_id == current_user.id)
        .first()
    )
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)
        db.flush()

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prefs, field, value)

    db.commit()
    db.refresh(prefs)
    return prefs


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a user: hide from listings and block authentication.

    Never a hard delete — 19 of the 20 foreign keys pointing at `users.id` are
    NO ACTION, so removing the row would either fail or force destroying
    legitimate history (Slack pipelines, code-review runs, watchers). Setting
    `deleted_at` keeps every owned row intact and keeps the call reversible.

    Admin-only, and you cannot delete yourself — locking the last admin out of
    their own dashboard is not a recoverable mistake from this UI.
    """
    if not current_user.role or current_user.role.name != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an admin can delete users",
        )
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.deleted_at = datetime.utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
