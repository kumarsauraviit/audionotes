import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth_schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.auth_service import (
    consume_reset_token,
    consume_verification_token,
    create_reset_token,
    create_verification_token,
    get_redis,
    queue_reset_email,
    queue_verification_email,
    revoke_refresh_token,
    rotate_refresh_token,
    store_refresh_token,
)
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.security import create_access_token, digest_token, get_current_user, hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["authentication"])
FORGOT_MESSAGE = "If an account exists with this email, a password reset link has been sent."


def check_rate_limit(request: Request, action: str) -> None:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    key = f"auth:rate:{action}:{client_ip}"
    try:
        client = get_redis()
        count = client.incr(key)
        if count == 1:
            client.expire(key, 60)
    except Exception as exc:
        logger.error("Authentication rate limiter unavailable: %s", exc)
        raise HTTPException(503, "Authentication service temporarily unavailable.") from exc
    if count > settings.auth_rate_limit_per_minute:
        raise HTTPException(429, "Too many authentication requests. Please try again later.")


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, "register")
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(name=payload.name, email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists.") from None
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not create user")
        raise HTTPException(500, "Could not complete registration.") from None
    try:
        verification_token = create_verification_token(db, user)
        queue_verification_email(user, verification_token)
    except Exception:
        db.rollback()
        logger.exception("Could not create email verification request for user %s", user.id)
    return RegisterResponse(message="Registration successful", user=user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, "login")
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password.", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(403, "This account is inactive.")
    if not user.is_verified:
        raise HTTPException(403, "Your email is not verified. Please verify your email address before logging in.")
    refresh_token = secrets.token_urlsafe(48)
    try:
        access_token, expires_in = create_access_token(user)
        store_refresh_token(get_redis(), refresh_token, user)
    except Exception as exc:
        logger.exception("Authentication token service unavailable")
        raise HTTPException(503, "Authentication service temporarily unavailable.") from exc
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    next_refresh = secrets.token_urlsafe(48)
    client = None
    try:
        client = get_redis()
        session = rotate_refresh_token(client, payload.refresh_token, next_refresh)
        if not session:
            raise HTTPException(401, "Invalid or expired refresh token.")
        user = db.get(User, session.get("user_id"))
        if not user or not user.is_active or user.token_version != session.get("token_version"):
            revoke_refresh_token(client, next_refresh)
            raise HTTPException(401, "Invalid or expired refresh token.")
        access_token, expires_in = create_access_token(user)
        return TokenResponse(access_token=access_token, refresh_token=next_refresh, expires_in=expires_in)
    except HTTPException:
        raise
    except Exception as exc:
        if client is not None:
            try:
                revoke_refresh_token(client, next_refresh)
            except Exception:
                logger.exception("Could not revoke unreturned refresh token")
        logger.exception("Refresh token service unavailable")
        raise HTTPException(503, "Authentication service temporarily unavailable.") from exc


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, "verify-email")
    try:
        verified = consume_verification_token(db, payload.token)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not verify email address")
        raise HTTPException(500, "Could not verify email address.") from exc
    if not verified:
        raise HTTPException(400, "Invalid or expired email verification token.")
    return MessageResponse(message="Email verified successfully.")


@router.post("/logout", response_model=MessageResponse)
def logout(
    payload: RefreshRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        client = get_redis()
        key = f"auth:refresh:{digest_token(payload.refresh_token)}"
        session = client.get(key)
        if session:
            import json
            if json.loads(session).get("user_id") != current_user.id:
                raise HTTPException(403, "Refresh token does not belong to this account.")
        revoke_refresh_token(client, payload.refresh_token)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not revoke refresh session")
        raise HTTPException(503, "Authentication service temporarily unavailable.") from exc
    return MessageResponse(message="Logged out successfully.")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, "forgot-password")
    user = db.scalar(select(User).where(User.email == payload.email, User.is_active.is_(True)))
    if user:
        try:
            token = create_reset_token(db, user)
            queue_reset_email(user, token)
        except Exception:
            db.rollback()
            logger.exception("Could not process password reset request")
            # Keep the response generic even when the address maps to no account.
    return MessageResponse(message=FORGOT_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(request, "reset-password")
    try:
        changed = consume_reset_token(db, payload.token, payload.new_password)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Could not reset password")
        raise HTTPException(500, "Could not reset password.") from exc
    if not changed:
        raise HTTPException(400, "Invalid or expired password reset token.")
    return MessageResponse(message="Password reset successful.")
