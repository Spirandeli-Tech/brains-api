from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.firebase import verify_firebase_token
from app.models.user import User

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: extracts Bearer token, verifies with Firebase,
    and returns the User from the database.

    Usage:
        @router.get("/protected")
        def protected_route(user: User = Depends(get_current_user)):
            ...
    """
    token = credentials.credentials

    try:
        decoded_token = verify_firebase_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    firebase_uid = decoded_token["uid"]
    user = db.query(User).filter(User.firebase_id == firebase_uid).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
