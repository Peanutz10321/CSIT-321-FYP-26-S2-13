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
from app.security.audit import audit_details, log_event
from app.services.user_service import build_user_account

router = APIRouter(prefix="/auth", tags=["Auth"])


# Roles a member of the public may self-assign at registration. System admin is
# never in this set: those accounts are provisioned out of band.
PUBLIC_REGISTRATION_ROLES = {UserRole.voter.value, UserRole.organizer.value}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def registerUser(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Public registration. Creates voter or organizer accounts.

    System admin remains a trusted role that can never be self-assigned and is
    rejected with 403. A self-registered organizer is recorded with an
    ``organizer_created`` audit event, committed atomically with the account.
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

    # System admin can never be registered from the public route.
    if request.role == UserRole.system_admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System admin accounts cannot be registered publicly",
        )

    # Only voter and organizer may be self-assigned; anything else (including
    # legacy role strings) is rejected.
    if request.role not in PUBLIC_REGISTRATION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be voter or organizer",
        )

    role = UserRole(request.role)

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
            detail="Account already exists.",
        )

    new_user = build_user_account(
        db,
        role=role,
        username=request.username,
        email=request.email,
        password=request.password,
    )

    db.add(new_user)

    try:
        if role == UserRole.organizer:
            # Flush first so the new id exists for the audit row; it raises the
            # same IntegrityError the commit would, so the duplicate path below
            # is unchanged. The organizer is the actor of their own creation
            # event, and details carry only the role — never any credentials.
            db.flush()
            log_event(
                db,
                actor_user_id=new_user.id,
                action="organizer_created",
                entity_type="user",
                entity_id=new_user.id,
                details=audit_details(role="organizer"),
            )
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

