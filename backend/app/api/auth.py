"""Authentication API endpoints (signup, login, me)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.token import TokenResponse
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.services.rate_limiter import RateLimiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(
    user_in: UserCreate,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Register a new user account."""
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists",
        )

    # If first user registered in system, assign admin role automatically
    user_count = db.query(User).count()
    role = "admin" if user_count == 0 else user_in.role

    user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        subject=user.id,
        extra_claims={"email": user.email, "role": user.role},
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(RateLimiter(times=10, seconds=10))],
)
def login(
    credentials: UserLogin,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email and password."""
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )

    token = create_access_token(
        subject=user.id,
        extra_claims={"email": user.email, "role": user.role},
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """Return the profile of the currently logged-in user."""
    return UserResponse.model_validate(current_user)
