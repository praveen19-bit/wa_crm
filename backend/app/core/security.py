"""Security helpers: password hashing + JWT tokens."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt
from fastapi import HTTPException, status

from ..config import settings


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (returns a str)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- jwt tokens
def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> tuple[str, datetime]:
    """Create a signed JWT. Returns (token, expiry_dt)."""
    expire_minutes = expires_minutes or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_token(token: str) -> dict[str, Any]:
    """Decode + validate a JWT. Raises HTTPException 401 when invalid/expired."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
        )
