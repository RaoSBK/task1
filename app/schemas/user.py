"""User Pydantic validation and serialization schemas."""

import re
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from app.schemas.enums import UserRole


def validate_password_strength(password: str) -> str:
    """Validate password requirements: minimum 8 chars, at least 1 letter and 1 digit."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit.")
    return password


class UserBase(BaseModel):
    """Base fields shared across user schemas."""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    role: UserRole = UserRole.CUSTOMER


class UserCreate(UserBase):
    """Internal/Admin payload for creating a user with a specific role."""
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class CustomerRegisterRequest(BaseModel):
    """Public customer registration request.

    Note: The 'role' field is strictly excluded. Extra fields (e.g. role escalation
    attempts) are discarded, and the user is always created with role=customer.
    """
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "name": "Jane Doe",
                "email": "jane.doe@example.com",
                "password": "SecurePassword123!",
            }
        },
    )

    name: str = Field(..., min_length=1, max_length=255, description="Full name")
    email: EmailStr = Field(..., description="Valid unique email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (minimum 8 characters, at least 1 letter and 1 digit)",
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserLoginRequest(BaseModel):
    """Login credentials payload."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "jane.doe@example.com",
                "password": "SecurePassword123!",
            }
        }
    )

    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., min_length=1, description="Password")


class UserRead(BaseModel):
    """Public representation of a user. Never exposes password_hash."""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Jane Doe",
                "email": "jane.doe@example.com",
                "role": "customer",
                "created_at": "2026-10-16T10:00:00Z",
            }
        },
    )

    id: int
    name: str
    email: str
    role: UserRole
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT Access Token response."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
                "user": {
                    "id": 1,
                    "name": "Jane Doe",
                    "email": "jane.doe@example.com",
                    "role": "customer",
                    "created_at": "2026-10-16T10:00:00Z",
                },
            }
        }
    )

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
