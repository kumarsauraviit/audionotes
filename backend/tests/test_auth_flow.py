from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta, timezone
import jwt

from app.database import Base, get_db
from app.main import app
from app.models import EmailVerificationToken, PasswordResetToken, User


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.counters = {}

    def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, *_args):
        return True

    def setex(self, key, _ttl, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    def eval(self, _script, _key_count, old_key, new_key, _ttl):
        value = self.values.pop(old_key, None)
        if value is not None:
            self.values[new_key] = value
        return value


@pytest.fixture
def auth_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    redis_client = FakeRedis()
    settings = SimpleNamespace(
        jwt_secret_key="test-only-secret-key-long-enough-for-tests",
        jwt_algorithm="HS256",
        access_token_expire_minutes=15,
        refresh_token_expire_days=30,
        password_reset_expire_minutes=30,
        email_verification_expire_hours=24,
        auth_rate_limit_per_minute=100,
    )

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("app.auth_routes.get_redis", lambda: redis_client)
    monkeypatch.setattr("app.auth_routes.get_settings", lambda: settings)
    monkeypatch.setattr("app.security.get_settings", lambda: settings)
    monkeypatch.setattr("app.auth_service.get_settings", lambda: settings)
    sent_reset_tokens = []
    sent_verification_tokens = []
    monkeypatch.setattr("app.auth_routes.queue_reset_email", lambda user, token: sent_reset_tokens.append((user.email, token)))
    monkeypatch.setattr(
        "app.auth_routes.queue_verification_email",
        lambda user, token: sent_verification_tokens.append((user.email, token)),
    )
    with TestClient(app) as client:
        yield client, testing_session, redis_client, sent_reset_tokens, sent_verification_tokens
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_register_validation_and_safe_response(auth_client):
    client = auth_client[0]
    bad_email = client.post("/api/auth/register", json={"name": "Test", "email": "invalid", "password": "StrongPassword123"})
    weak_password = client.post("/api/auth/register", json={"name": "Test", "email": "test@example.com", "password": "weakpassword"})
    assert bad_email.status_code == 422
    assert weak_password.status_code == 422

    response = client.post(
        "/api/auth/register",
        json={"name": " Test User ", "email": "TEST@example.com", "password": "StrongPassword123"},
    )
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "test@example.com"
    assert "password_hash" not in response.text
    duplicate = client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "StrongPassword123"},
    )
    assert duplicate.status_code == 409

    with auth_client[1]() as db:
        user = db.scalar(select(User).where(User.email == "test@example.com"))
        assert user.password_hash != "StrongPassword123"
        assert user.password_hash.startswith("$argon2")


def test_login_me_rotation_logout_and_replay_rejection(auth_client):
    client, sessions, _redis, _reset_tokens, verification_tokens = auth_client
    client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "StrongPassword123"},
    )
    # Unverified user cannot login
    unverified_login = client.post("/api/auth/login", json={"email": "test@example.com", "password": "StrongPassword123"})
    assert unverified_login.status_code == 403
    assert "not verified" in unverified_login.json()["detail"].lower()

    # Verify user email
    _email, v_token = verification_tokens[0]
    verify_res = client.post("/api/auth/verify-email", json={"token": v_token})
    assert verify_res.status_code == 200

    bad_login = client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrongpassword"})
    assert bad_login.status_code == 401
    login = client.post("/api/auth/login", json={"email": "TEST@example.com", "password": "StrongPassword123"})
    assert login.status_code == 200
    tokens = login.json()
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"
    assert me.json()["is_verified"] is True
    assert "password_hash" not in me.text
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    refresh_as_access = jwt.encode(
        {"sub": "user-id", "type": "refresh", "jti": "test", "ver": 0,
         "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(minutes=1)},
        "test-only-secret-key-long-enough-for-tests", algorithm="HS256",
    )
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh_as_access}"}).status_code == 401

    rotated = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != tokens["refresh_token"]
    replay = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401

    logout = client.post(
        "/api/auth/logout",
        json={"refresh_token": rotated.json()["refresh_token"]},
        headers={"Authorization": f"Bearer {rotated.json()['access_token']}"},
    )
    assert logout.status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}).status_code == 401


def test_forgot_password_is_generic_and_reset_is_single_use(auth_client):
    client, sessions, _redis, sent_tokens, verification_tokens = auth_client
    client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "StrongPassword123"},
    )
    _email, v_token = verification_tokens[0]
    client.post("/api/auth/verify-email", json={"token": v_token})

    original_login = client.post(
        "/api/auth/login", json={"email": "test@example.com", "password": "StrongPassword123"}
    ).json()
    existing = client.post("/api/auth/forgot-password", json={"email": "test@example.com"})
    missing = client.post("/api/auth/forgot-password", json={"email": "absent@example.com"})
    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json()
    assert len(sent_tokens) == 1
    email, token = sent_tokens[0]
    assert email == "test@example.com"
    with sessions() as db:
        row = db.scalar(select(PasswordResetToken))
        assert row.token_hash != token

    reset = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "AnotherStrong456"},
    )
    assert reset.status_code == 200
    stale_session = client.post(
        "/api/auth/refresh", json={"refresh_token": original_login["refresh_token"]}
    )
    assert stale_session.status_code == 401
    reused = client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "OtherStrong789"},
    )
    assert reused.status_code == 400
    assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "StrongPassword123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "test@example.com", "password": "AnotherStrong456"}).status_code == 200


def test_inactive_account_and_expired_reset_token(auth_client):
    client, sessions, _redis, sent_tokens, verification_tokens = auth_client
    client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "StrongPassword123"},
    )
    _email, v_token = verification_tokens[0]
    client.post("/api/auth/verify-email", json={"token": v_token})

    with sessions() as db:
        user = db.scalar(select(User).where(User.email == "test@example.com"))
        user.is_active = False
        db.commit()
    inactive = client.post(
        "/api/auth/login", json={"email": "test@example.com", "password": "StrongPassword123"}
    )
    assert inactive.status_code == 403
    with sessions() as db:
        user = db.scalar(select(User).where(User.email == "test@example.com"))
        user.is_active = True
        db.commit()
    client.post("/api/auth/forgot-password", json={"email": "test@example.com"})
    _email, token = sent_tokens[0]
    with sessions() as db:
        row = db.scalar(select(PasswordResetToken))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    expired = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "AnotherStrong456"}
    )
    assert expired.status_code == 400


def test_email_verification_is_hashed_and_single_use(auth_client):
    client, sessions, _redis, _reset_tokens, verification_tokens = auth_client
    registered = client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "StrongPassword123"},
    )
    assert registered.status_code == 201
    email, token = verification_tokens[0]
    assert email == "test@example.com"
    with sessions() as db:
        verification = db.scalar(select(EmailVerificationToken))
        assert verification.token_hash != token
        assert not db.scalar(select(User).where(User.email == email)).is_verified
    response = client.post("/api/auth/verify-email", json={"token": token})
    assert response.status_code == 200
    reused = client.post("/api/auth/verify-email", json={"token": token})
    assert reused.status_code == 400
    with sessions() as db:
        assert db.scalar(select(User).where(User.email == email)).is_verified


def test_unverified_user_cannot_access_notes(auth_client):
    client, sessions, _redis, _reset_tokens, _verification_tokens = auth_client
    # Directly create an unverified user in DB and generate a token
    with sessions() as db:
        user = User(name="Unverified", email="unverified@example.com", password_hash="hash", is_verified=False)
        db.add(user)
        db.commit()
        db.refresh(user)
        from app.security import create_access_token
        token, _ = create_access_token(user)

    # Attempt to list notes with unverified user token
    res = client.get("/api/notes", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert "verify" in res.json()["detail"].lower()


