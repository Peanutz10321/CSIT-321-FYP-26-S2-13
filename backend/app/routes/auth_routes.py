from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth_schema import RegisterRequest, LoginRequest, AuthResponse
from app.schemas.user_schema import UserResponse
from email_validator import validate_email, EmailNotValidError
from app.security.password import verify_password
from app.security.jwt import create_access_token
from app.services.user_service import build_user_account

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def registerUser(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Public registration. Creates voter accounts only.

    Organizer and system admin are trusted roles and must never be
    self-assigned: organizers create elections and trigger tallies. Organizers
    are provisioned by a system admin via POST /admin/users/organizers.
    """

    if not request.username or not request.username.strip() \
            or not request.email or not request.email.strip() \
            or not request.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing field detected. Please key in again.",
        )

    try:
        validate_email(request.email, check_deliverability=False)
    except EmailNotValidError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing field detected. Please key in again.",
        )

    # Admin cannot register from public route
    if request.role == UserRole.system_admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System admin accounts cannot be registered publicly",
        )

    # Organizer is a trusted role and cannot be self-assigned.
    if request.role == UserRole.organizer.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Organizer accounts cannot be registered publicly. "
                "Contact a system administrator."
            ),
        )

    # Public registration creates voters only.
    if request.role != UserRole.voter.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be voter",
        )

    # Check duplicate email
    existing_email = db.query(User).filter(User.email == request.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account already exists.",
        )

    existing_username = db.query(User).filter(User.username == request.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists.",
        )

    new_user = build_user_account(
        db,
        role=UserRole.voter,
        username=request.username,
        email=request.email,
        password=request.password,
    )

    db.add(new_user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account could not be created. Please try again.",
        )

    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=AuthResponse)
def loginUser(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Login for voter, organizer, and system admin.
    Suspended users cannot login.
    """

    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please provide a valid email and password",
        )

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please provide a valid email and password",
        )

    if user.status == UserStatus.suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please provide a valid email and password",
        )

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={
            "role": user.role.value,
            "email": user.email,
        },
    )

    return AuthResponse(access_token=access_token)

