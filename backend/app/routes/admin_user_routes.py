from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.schemas.user_schema import (
    OrganizerCreateRequest,
    UserResponse,
    UserStatusUpdateRequest,
)
from app.security.audit import audit_details, log_event
from app.security.security import require_system_admin
from app.services.user_service import build_user_account


router = APIRouter(prefix="/admin/users", tags=["Admin Users"])


def _apply_status_change(
    db: Session,
    *,
    actor_user_id: UUID,
    user: User,
    new_status: UserStatus,
) -> bool:
    """Apply a status change and audit it, sharing one classification across the
    generic status, suspend and unsuspend routes.

    Returns True if the status actually changed. A no-op (the account is already
    in ``new_status``) makes no change and records no event — so re-suspending an
    already-suspended user, or a generic ``/status`` to the current value, does
    not litter the trail.

    The event action reflects the real transition:

      * into suspended      -> user_suspended
      * out of suspended     -> user_unsuspended
      * any other transition -> user_status_changed

    so the generic ``/status`` route and the dedicated suspend/unsuspend routes
    produce identical semantics for the same transition. The target account is
    identified by the audit row's entity_id; details carry only the two statuses,
    never an email, username, or external id.
    """
    old_status = user.status
    if old_status == new_status:
        return False

    user.status = new_status

    if new_status == UserStatus.suspended:
        action = "user_suspended"
    elif old_status == UserStatus.suspended:
        action = "user_unsuspended"
    else:
        action = "user_status_changed"

    log_event(
        db,
        actor_user_id=actor_user_id,
        action=action,
        entity_type="user",
        entity_id=user.id,
        details=audit_details(
            old_status=old_status.value,
            new_status=new_status.value,
        ),
    )
    return True


@router.post(
    "/organizers",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def createOrganizer(
    body: OrganizerCreateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_system_admin),
):
    """
    Provision an organizer account. System admin only.

    Organizer is a trusted role (election creation, tally triggering), so it is
    rejected on the public registration route and can only be created here.
    """

    existing_email = db.query(User).filter(User.email == body.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account already exists.",
        )

    existing_username = db.query(User).filter(User.username == body.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists.",
        )

    organizer = build_user_account(
        db,
        role=UserRole.organizer,
        username=body.username,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
    )

    db.add(organizer)

    try:
        # Flush first so the new id exists for the audit row. It raises the same
        # IntegrityError the commit would, so the duplicate path is unchanged.
        db.flush()
        log_event(
            db,
            actor_user_id=current_admin.id,
            action="organizer_created",
            entity_type="user",
            entity_id=organizer.id,
            details=audit_details(role="organizer"),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account could not be created. Please try again.",
        )

    db.refresh(organizer)

    return organizer


@router.get("", response_model=list[UserResponse])
def listUsers(
    search: Optional[str] = Query(default=None),
    role: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_system_admin),
):
    """
    System admin can view/search user accounts.
    Search checks username, email, and external ID.
    """

    query = db.query(User).filter(User.id != current_admin.id)

    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.email.ilike(keyword),
                User.external_id.ilike(keyword),
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
def viewUser(
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


@router.patch("/{user_id}/status", response_model=UserResponse)
def updateUserStatus(
    user_id: UUID,
    body: UserStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_system_admin),
):
    """
    System admin can set a user's status to active, inactive, or suspended.
    """

    if body.status not in [item.value for item in UserStatus]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {[s.value for s in UserStatus]}",
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own status",
        )

    # Same transition helper the suspend/unsuspend routes use, so a generic
    # /status to "suspended" is audited as user_suspended, and a no-op records
    # nothing.
    _apply_status_change(
        db,
        actor_user_id=current_admin.id,
        user=user,
        new_status=UserStatus(body.status),
    )

    db.commit()
    db.refresh(user)

    return user


@router.patch("/{user_id}/suspend", response_model=UserResponse)
def suspendUser(
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
            detail="You cannot change your own status",
        )

    _apply_status_change(
        db,
        actor_user_id=current_admin.id,
        user=user,
        new_status=UserStatus.suspended,
    )

    db.commit()
    db.refresh(user)

    return user


@router.patch("/{user_id}/unsuspend", response_model=UserResponse)
def unsuspendUser(
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

    if user.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own status",
        )

    _apply_status_change(
        db,
        actor_user_id=current_admin.id,
        user=user,
        new_status=UserStatus.active,
    )

    db.commit()
    db.refresh(user)

    return user