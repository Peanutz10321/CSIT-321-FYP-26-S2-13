from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import GROUP_MAX_LENGTH, User, UserRole
from app.schemas.user_schema import UserResponse, UserUpdateRequest
from app.security.password import hash_password
from app.security.security import get_current_user
from app.services.user_service import get_all_group_names, get_users_by_group


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
                detail="Account already exists",
            )

        current_user.email = request.email

    if request.password:
        current_user.password_hash = hash_password(request.password)

    # An account holder may join, change or leave an organisation. Blank and
    # whitespace-only input becomes NULL, exactly as at registration, so leaving a
    # group cannot leave an empty string behind that would show up as a selectable
    # organisation. Only a request that actually carries the field touches it —
    # model_fields_set is what separates "clear this" from "I did not mention it",
    # since None means both otherwise.
    if "group" in request.model_fields_set:
        current_user.group = (request.group or "").strip() or None

    db.commit()
    db.refresh(current_user)

    return current_user


def _require_group_reader(current_user: User) -> None:
    """Only organizers and system admins may browse the group directory.

    KNOWN LIMITATION: this is role-based only — any organizer can enumerate every
    group and read the voters in it, not just groups they have some relationship
    with. Narrowing that to a real membership/ownership model is deliberately out of
    scope here and is tracked separately.
    """
    if current_user.role not in (UserRole.organizer, UserRole.system_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organizers and admins can view groups",
        )


@router.get("/groups", response_model=list[str])
def getGroupNames(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List the organisation names that have at least one active voter.
    """
    _require_group_reader(current_user)

    return get_all_group_names(db)


@router.get("/by-group", response_model=list[UserResponse])
def getUsersByGroupName(
    group_name: str = Query(..., min_length=1, max_length=GROUP_MAX_LENGTH),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List the active voters in one organisation.

    The name is a query parameter rather than a path segment. Group names are
    organizer-authored free text that routinely contains '/', '&' and non-ASCII
    characters, and a '/' in a path segment is a route boundary no amount of
    percent-encoding reliably survives (proxies and ASGI servers normalise %2F
    inconsistently). A query parameter has none of that ambiguity.

    Required and bounded to the column width, so an empty or oversized value is a
    422 naming the field instead of a database error. An unknown group is still an
    empty list, not the 404 the commented draft raised: the caller is asking "who is
    in this group", and "nobody" is a real answer the create-election form renders
    on its own.
    """
    _require_group_reader(current_user)

    return get_users_by_group(db, group_name)
