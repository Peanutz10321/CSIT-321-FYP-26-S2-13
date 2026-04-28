from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth_schema import RegisterRequest, LoginRequest, AuthResponse
from app.schemas.user_schema import UserResponse
from app.security.password import hash_password, verify_password
from app.security.jwt import create_access_token


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Public registration.
    Only student and teacher accounts can be registered publicly.
    System admin accounts must NOT be publicly registered.
    """

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
            detail="Account with this email already exists",
        )

    # Check duplicate username
    existing_username = db.query(User).filter(User.username == request.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    # Check duplicate institution_id
    existing_institution_id = (
        db.query(User)
        .filter(User.institution_id == request.institution_id)
        .first()
    )
    if existing_institution_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Institution ID already exists",
        )

    new_user = User(
        institution_id=request.institution_id,
        username=request.username,
        full_name=request.full_name,
        email=request.email,
        password_hash=hash_password(request.password),
        role=UserRole(request.role),
        status=UserStatus.active,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
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
            detail="Your account has been suspended",
        )

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={
            "role": user.role.value,
            "email": user.email,
        },
    )

    return AuthResponse(access_token=access_token)