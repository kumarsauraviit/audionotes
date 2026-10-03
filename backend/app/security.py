import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return password_hash.verify(password, encoded_hash)
    except (ValueError, TypeError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(user: User) -> tuple[str, int]:
    settings = get_settings()
    if len(settings.jwt_secret_key.encode("utf-8")) < 32:
        raise RuntimeError("JWT_SECRET_KEY must contain at least 32 bytes of secret material.")
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": user.id,
            "type": "access",
            "jti": secrets.token_urlsafe(16),
            "ver": user.token_version,
            "iat": now,
            "exp": now + lifetime,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    if len(settings.jwt_secret_key.encode("utf-8")) < 32:
        raise RuntimeError("JWT_SECRET_KEY must contain at least 32 bytes of secret material.")
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "iat", "sub", "type", "jti", "ver"]},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or expired authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials)
        if claims.get("type") != "access" or not claims.get("sub"):
            raise unauthorized
        user = db.get(User, claims["sub"])
        if not user or not user.is_active or claims.get("ver") != user.token_version:
            raise unauthorized
        return user
    except (jwt.InvalidTokenError, KeyError):
        raise unauthorized from None


def get_current_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address first to use this feature.",
        )
    return current_user


def get_current_user_from_token_or_header(
    raw_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
) -> User:
    token_str = (credentials.credentials if credentials and credentials.credentials else raw_token) or ""
    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or expired authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token_str:
        raise unauthorized
    try:
        claims = decode_access_token(token_str)
        if claims.get("type") != "access" or not claims.get("sub"):
            raise unauthorized
        user = db.get(User, claims["sub"])
        if not user or not user.is_active or claims.get("ver") != user.token_version:
            raise unauthorized
        return user
    except (jwt.InvalidTokenError, KeyError):
        raise unauthorized from None


def get_current_verified_user_from_token_or_header(
    raw_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
) -> User:
    user = get_current_user_from_token_or_header(raw_token, credentials, db)
    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address first to use this feature.",
        )
    return user


