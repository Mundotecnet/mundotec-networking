from cryptography.fernet import Fernet
from passlib.context import CryptContext
import os

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Fernet (credentials) ──────────────────────────────────────────────────────

def _fernet() -> Fernet:
    key = os.getenv("FERNET_KEY", "")
    if not key:
        raise RuntimeError("FERNET_KEY no está configurada")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(text: str) -> str | None:
    if not text:
        return None
    return _fernet().encrypt(text.encode()).decode()


def decrypt(text: str) -> str | None:
    if not text:
        return None
    return _fernet().decrypt(text.encode()).decode()


# ── bcrypt (passwords) ────────────────────────────────────────────────────────

def hash_pw(password: str) -> str:
    return _pwd_context.hash(password)


def verify_pw(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)
