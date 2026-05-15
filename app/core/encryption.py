from cryptography.fernet import Fernet

from app.core.config import settings


def _get_fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def mask_pat(pat: str) -> str:
    if len(pat) <= 4:
        return "****"
    return "****" + pat[-4:]
