"""Authentication routes (Part 10)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.api.deps import CurrentUser, DbSession
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.models import Role, User
from backend.app.schemas.api import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalars().first()

    # Same error and same code path for unknown email and wrong password.
    # Distinguishing them tells an attacker which emails are registered.
    if user is None or not verify_password(payload.password, user.hashed_password):
        logger.warning("failed login for %s", payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    return TokenResponse(
        access_token=create_access_token(user.email, user.role.value),
        expires_in_minutes=settings.jwt_expire_minutes,
    )


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, role=user.role.value)


def ensure_user(db, email: str, password: str, full_name: str, role: Role) -> User:
    """Idempotent user creation. Used by scripts/seed.py, not exposed as a route."""
    existing = db.execute(select(User).where(User.email == email)).scalars().first()
    if existing:
        return existing
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    return user
