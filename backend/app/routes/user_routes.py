from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.user import User, UserRole
from app.models.user import User
from app.schemas.user_schema import UserResponse, UserUpdateRequest
from app.security.password import hash_password
from app.security.security import get_current_user
from app.services.user_service import get_users_by_group, get_all_group_names


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
def getCurrentUser(
    current_user: User = Depends(get_current_user),
):
    """
    View own user account.
    """

    return current_user


@router.put("/me", response_model=UserResponse)
def updateCurrentUser(
    request: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update own user account.
    User can update username, email, and password.
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

    if request.password:
        current_user.password_hash = hash_password(request.password)

    db.commit()
    db.refresh(current_user)

    return current_user

#     @router.get("/groups", response_model=List[str])
# def get_group_names(
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     """
#     Get a list of all available organization names.
#     Access is restricted to organizers and system administrators only.
#     """
#     # Access control check: Only organizers and system administrators can view this.
#     if current_user.role not in [UserRole.organizer, UserRole.system_admin]:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Only organizers and admins can view group list",
#         )
    
#     groups = get_all_group_names(db)
#     return groups


# @router.get("/by-group/{group_name}", response_model=List[UserResponse])
# def get_users_by_group_name(
#     group_name: str,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     """
#     Retrieve all active voters of an organization based on its name.
#     Access is restricted to organizers and system administrators only.
#     """
#     # Access control check: Only organizers and system administrators can view this.
#     if current_user.role not in [UserRole.organizer, UserRole.system_admin]:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Only organizers and admins can view users by group",
#         )
    
#     users = get_users_by_group(db, group_name)
#     if not users:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"No active voters found in group: {group_name}",
#         )
    
#     return users
