import random

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth_schema import RegisterRequest, LoginRequest, AuthResponse
from app.schemas.user_schema import UserResponse
from email_validator import validate_email, EmailNotValidError
from app.security.password import hash_password, verify_password
from app.security.jwt import create_access_token

_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Quinn",
    "Avery", "Peyton", "Reese", "Skyler", "Drew", "Blake", "Cameron", "Dana",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Wilson", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Lee",
]

def _generate_full_name() -> str:
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def registerUser(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Public registration.
    Only student and teacher accounts can be registered publicly.
    System admin accounts must NOT be publicly registered.
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

    # Only allow student or teacher
    if request.role not in [UserRole.student.value, UserRole.teacher.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be either student or teacher",
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

    # Generate institution_id: STU-001 for students, TCH-001 for teachers
    role_enum = UserRole(request.role)
    prefix = "STU" if role_enum == UserRole.student else "TCH"
    existing_ids = (
        db.query(User.institution_id)
        .filter(User.role == role_enum)
        .all()
    )
    max_num = 0
    for (iid,) in existing_ids:
        try:
            num = int(iid.split("-")[1])
            if num > max_num:
                max_num = num
        except (IndexError, ValueError):
            pass
    institution_id = f"{prefix}-{max_num + 1:03d}"

    new_user = User(
        institution_id=institution_id,
        username=request.username,
        full_name=_generate_full_name(),
        email=request.email,
        password_hash=hash_password(request.password),
        role=role_enum,
        status=UserStatus.active,
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
    Login for student, teacher, and system admin.
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

