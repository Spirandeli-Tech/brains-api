import firebase_admin
from firebase_admin import credentials, auth
from app.core.config import settings


def init_firebase() -> None:
    """Initialize Firebase Admin SDK. Call once at application startup."""
    if firebase_admin._apps:
        return

    if settings.FIREBASE_SERVICE_ACCOUNT_PATH:
        cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()


def verify_firebase_token(id_token: str) -> dict:
    """Verify a Firebase ID token and return the decoded token claims."""
    decoded_token = auth.verify_id_token(id_token)
    return decoded_token
