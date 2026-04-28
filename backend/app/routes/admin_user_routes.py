from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.schemas.user_schema import UserResponse
from app.security.security import require_system_admin


router = APIRouter(prefix="/admin/users", tags=["Admin Users"])


@router.get("", response_model=list[UserResponse])
def list_users(
    search: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_system_admin),
):
    """
    System admin can view/search user accounts.
    Search checks username, full name, email, and institution ID.
    """

    query = db.query(User)

    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.full_name.ilike(keyword),
                User.email.ilike(keyword),
                User.institution_id.ilike(keyword),
            )
        )

    if role:
        if role not in [item.value for item in UserRole]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role",
            )
        query = query.filter(User.role == UserRole(role))

    if status_filter:
        if status_filter not in [item.value for item in UserStatus]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status",
            )
        query = query.filter(User.status == UserStatus(status_filter))

    return query.order_by(User.created_at.desc()).all()


@router.get("/{user_id}", response_model=UserResponse)
def view_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_system_admin),
):
    """
    System admin can view a specific user account.
    """

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@router.patch("/{user_id}/suspend", response_model=UserResponse)
def suspend_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_system_admin),
):
    """
    System admin can suspend a user account.
    """

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot suspend your own account",
        )

    user.status = UserStatus.suspended
    db.commit()
    db.refresh(user)

    return user


@router.patch("/{user_id}/unsuspend", response_model=UserResponse)
def unsuspend_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_system_admin),
):
    """
    System admin can unsuspend a user account.
    """

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.status = UserStatus.active
    db.commit()
    db.refresh(user)

    return user