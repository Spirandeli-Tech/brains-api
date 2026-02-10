from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.firebase import verify_firebase_token
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.auth import RegisterRequest, LoginRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    try:
        decoded_token = verify_firebase_token(request.firebase_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase token",
        )

    firebase_uid = decoded_token["uid"]
    email = decoded_token.get("email")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase account must have an email address",
        )

    existing_user = db.query(User).filter(
        (User.firebase_id == firebase_uid) | (User.email == email)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )

    client_role = db.query(UserRole).filter(UserRole.name == "CLIENT").first()

    new_user = User(
        email=email,
        first_name=request.first_name,
        last_name=request.last_name,
        firebase_id=firebase_uid,
        role_id=client_role.id if client_role else None,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=UserResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        decoded_token = verify_firebase_token(request.firebase_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase token",
        )

    firebase_uid = decoded_token["uid"]

    user = db.query(User).filter(User.firebase_id == firebase_uid).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first.",
        )

    user.last_login = datetime.utcnow()
    db.commit()
    db.refresh(user)

    return user
