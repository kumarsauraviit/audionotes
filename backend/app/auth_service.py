import json
import logging
from functools import lru_cache
from datetime import datetime, timedelta, timezone

import redis
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailVerificationToken, PasswordResetToken, User
from app.security import digest_token, hash_password, new_refresh_token

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


def refresh_ttl_seconds() -> int:
    return get_settings().refresh_token_expire_days * 24 * 60 * 60


def store_refresh_token(client: redis.Redis, token: str, user: User) -> None:
    client.setex(
        f"auth:refresh:{digest_token(token)}",
        refresh_ttl_seconds(),
        json.dumps({"user_id": user.id, "token_version": user.token_version}),
    )


ROTATE_REFRESH_SCRIPT = """
local session = redis.call('GET', KEYS[1])
if not session then return nil end
redis.call('DEL', KEYS[1])
redis.call('SETEX', KEYS[2], ARGV[1], session)
return session
"""


def rotate_refresh_token(client: redis.Redis, old_token: str, new_token: str) -> dict | None:
    result = client.eval(
        ROTATE_REFRESH_SCRIPT,
        2,
        f"auth:refresh:{digest_token(old_token)}",
        f"auth:refresh:{digest_token(new_token)}",
        refresh_ttl_seconds(),
    )
    return json.loads(result) if result else None


def revoke_refresh_token(client: redis.Redis, token: str) -> None:
    client.delete(f"auth:refresh:{digest_token(token)}")


def create_reset_token(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc)
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    token = new_refresh_token()
    expires_at = now + timedelta(minutes=get_settings().password_reset_expire_minutes)
    db.add(PasswordResetToken(user_id=user.id, token_hash=digest_token(token), expires_at=expires_at))
    db.commit()
    return token


def create_verification_token(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc)
    db.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user.id, EmailVerificationToken.used_at.is_(None))
        .values(used_at=now)
    )
    token = new_refresh_token()
    expires_at = now + timedelta(hours=get_settings().email_verification_expire_hours)
    db.add(EmailVerificationToken(user_id=user.id, token_hash=digest_token(token), expires_at=expires_at))
    db.commit()
    return token


def consume_verification_token(db: Session, token: str) -> bool:
    now = datetime.now(timezone.utc)
    verification = db.scalar(
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.token_hash == digest_token(token),
            EmailVerificationToken.used_at.is_(None),
        )
        .with_for_update()
    )
    if not verification:
        return False
    expires_at = verification.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        return False
    user = db.get(User, verification.user_id)
    if not user:
        return False
    user.is_verified = True
    verification.used_at = now
    db.commit()
    return True


def consume_reset_token(db: Session, token: str, new_password: str) -> bool:
    now = datetime.now(timezone.utc)
    reset = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == digest_token(token), PasswordResetToken.used_at.is_(None))
        .with_for_update()
    )
    if not reset:
        return False
    expires_at = reset.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        return False
    user = db.get(User, reset.user_id)
    if not user:
        return False
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    reset.used_at = now
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != reset.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    db.commit()
    return True


def queue_reset_email(user: User, token: str) -> None:
    from app.tasks import send_password_reset_email_task

    try:
        send_password_reset_email_task.delay(user.email, token)
    except Exception:
        logger.error("Could not queue password reset email for user %s", user.id)


def queue_verification_email(user: User, token: str) -> None:
    from app.tasks import send_email_verification_task

    try:
        send_email_verification_task.delay(user.email, token)
    except Exception:
        logger.error("Could not queue email verification for user %s", user.id)
