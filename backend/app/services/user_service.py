"""
Shared user-account provisioning.

Public registration creates both voter and organizer accounts through this one
builder. Keeping the external-id sequence and account construction here means the
role-specific numbering (VOTER-### and ORG-###) is produced in exactly one place.
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
    group: str | None = None,
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
        group=(group or "").strip() or None,
    )


def get_all_group_names(db: Session) -> list[str]:
    """Every distinct group that currently has at least one active voter in it.

    Groups with no selectable members are left out, so an organizer is never shown
    an option that would resolve to an empty voter list.
    """
    rows = (
        db.query(User.group)
        .filter(
            User.group.isnot(None),
            User.group != "",
            User.role == UserRole.voter,
            User.status == UserStatus.active,
        )
        .distinct()
        .all()
    )

    return sorted(group for (group,) in rows if group)


def get_users_by_group(db: Session, group_name: str) -> list[User]:
    """The active voters in one group, matched exactly.

    Only active voters are returned because these are the accounts an organizer can
    actually enrol — an organizer, a suspended account, or a pending one would be
    rejected by the election routes anyway.

    The commented scaffolding also carried a partial/ilike variant. It is left out:
    nothing calls it, and a fuzzy match would silently pull in members of a
    different organisation whose name happens to share a prefix.
    """
    if not group_name or not group_name.strip():
        return []

    return (
        db.query(User)
        .filter(
            User.group == group_name.strip(),
            User.role == UserRole.voter,
            User.status == UserStatus.active,
        )
        .order_by(User.external_id)
        .all()
    )
