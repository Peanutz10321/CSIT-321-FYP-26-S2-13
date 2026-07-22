"""
Shared user-account provisioning.

Public registration and admin-only organizer provisioning both create User rows.
Keeping the external-id sequence and account construction here means the two
paths cannot drift apart (e.g. produce different ORG-### numbering).
"""

import random

from sqlalchemy.orm import Session

from app.models.user import User, UserRole, UserStatus
from app.security.password import hash_password


_EXTERNAL_ID_PREFIXES = {
    UserRole.voter: "VOTER",
    UserRole.organizer: "ORG",
    UserRole.system_admin: "ADMIN",
}

_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Quinn",
    "Avery", "Peyton", "Reese", "Skyler", "Drew", "Blake", "Cameron", "Dana",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Wilson", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Lee",
]


def generate_full_name() -> str:
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"


def generate_external_id(db: Session, role: UserRole) -> str:
    """Next sequential external id for a role, e.g. VOTER-001 or ORG-001."""
    prefix = _EXTERNAL_ID_PREFIXES[role]

    existing_external_ids = (
        db.query(User.external_id)
        .filter(User.role == role)
        .all()
    )

    max_num = 0
    for (existing_external_id,) in existing_external_ids:
        try:
            num = int(existing_external_id.split("-")[1])
        except (IndexError, ValueError):
            continue
        if num > max_num:
            max_num = num

    return f"{prefix}-{max_num + 1:03d}"


def build_user_account(
    db: Session,
    *,
    role: UserRole,
    username: str,
    email: str,
    password: str,
    full_name: str | None = None,
) -> User:
    """Construct an active User and add it to the session (caller commits)."""
    return User(
        external_id=generate_external_id(db, role),
        username=username,
        full_name=full_name or generate_full_name(),
        email=email,
        password_hash=hash_password(password),
        role=role,
        status=UserStatus.active,
    )
