"""Token and authentication schemas."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.user import UserResponse


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenPayload(BaseModel):
    sub: str
    exp: int | None = None
    role: str | None = None
