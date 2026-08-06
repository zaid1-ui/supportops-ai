"""User management routes — Admin only (role differentiation).

Admin is the platform administrator: managing users, roles, and activation is
their domain, separate from the Lead's operational decision-making. These
routes are gated with require_role(Role.ADMIN), so a Lead (or anyone else)
cannot manage users even though they share the same approval authority.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.api.deps import AdminUser, DbSession
from backend.app.core.security import hash_password
from backend.app.models import Role, User
from backend.app.schemas.api import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users(db: DbSession, _: AdminUser) -> list[UserResponse]:
    """List all users. Admin only."""
    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    return [_to_response(u) for u in users]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: DbSession, _: AdminUser) -> UserResponse:
    """Create a user with a role. Admin only."""
    existing = db.execute(select(User).where(User.email == payload.email)).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User already exists: {payload.email}",
        )

    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    return _to_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: str, payload: UserUpdate, db: DbSession, admin: AdminUser) -> UserResponse:
    """Update a user's name, password, role, or active state. Admin only."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such user")

    # Prevent an admin from deactivating or demoting themselves — that would
    # lock the platform out of its own administration.
    if user.id == admin.id:
        if payload.role is not None and payload.role is not Role.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot change your own role away from admin",
            )
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot deactivate your own account",
            )

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    return _to_response(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_user(user_id: str, db: DbSession, admin: AdminUser) -> None:
    """Delete a user. Admin only. Cannot delete yourself."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such user")
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Cannot delete your own account"
        )

    db.delete(user)
    db.commit()


def _to_response(u: User) -> UserResponse:
    return UserResponse(id=u.id, email=u.email, full_name=u.full_name, role=u.role.value)

