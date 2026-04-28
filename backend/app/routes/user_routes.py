from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user_schema import UserResponse, UserUpdateRequest
from app.security.password import hash_password
from app.security.security import get_current_user


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def view_own_account(
    current_user: User = Depends(get_current_user),
):
    """
    View own user account.
    """

    return current_user


@router.put("/me", response_model=UserResponse)
def update_own_account(
    request: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update own user account.
    User can update username, full name, email, and password.
    """

    if request.username and request.username != current_user.username:
        existing_username = (
            db.query(User)
            .filter(User.username == request.username)
            .filter(User.id != current_user.id)
            .first()
        )

        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

        current_user.username = request.username

    if request.email and request.email != current_user.email:
        existing_email = (
            db.query(User)
            .filter(User.email == request.email)
            .filter(User.id != current_user.id)
            .first()
        )

        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account with this email already exists",
            )

        current_user.email = request.email

    if request.full_name:
        current_user.full_name = request.full_name

    if request.password:
        current_user.password_hash = hash_password(request.password)

    db.commit()
    db.refresh(current_user)

    return current_user