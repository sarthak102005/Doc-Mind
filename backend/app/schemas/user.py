"""User schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

EMAIL_PATTERN = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"


class UserBase(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, description="Valid user email address")
    full_name: str | None = None


class UserCreate(UserBase):
    password: str = Field(min_length=6, description="Plaintext password (min 6 characters)")
    role: str = Field(default="user", pattern="^(user|admin)$")


class UserLogin(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    is_active: bool
    created_at: datetime
