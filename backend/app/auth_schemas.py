from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security import normalize_email


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank.")
        return value

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not (any(c.islower() for c in value) and any(c.isupper() for c in value) and any(c.isdigit() for c in value)):
            raise ValueError("Password must include an uppercase letter, a lowercase letter, and a number.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return normalize_email(value)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not (any(c.islower() for c in value) and any(c.isupper() for c in value) and any(c.isdigit() for c in value)):
            raise ValueError("Password must include an uppercase letter, a lowercase letter, and a number.")
        return value


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    is_verified: bool
    model_config = ConfigDict(from_attributes=True)


class RegisterResponse(BaseModel):
    message: str
    user: UserResponse


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    message: str
