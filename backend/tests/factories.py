"""
Shared account provisioning for tests.

Public registration creates voters only (see PR 2 / the remediation plan), so
tests that merely *need* an organizer to exist can no longer POST to
/auth/register. They provision one directly instead.

Direct insertion is deliberate: these are fixtures, not assertions about the
provisioning route. The admin-only provisioning endpoint itself is covered by
tests/test_auth_user_admin_routes.py.
"""

from uuid import uuid4

from app.database import SessionLocal
from app.models.user import User, UserRole, UserStatus
from app.security.password import hash_password


DEFAULT_PASSWORD = "testing123"


def create_user_directly(
    role: UserRole,
    *,
    username: str,
    email: str,
    password: str = DEFAULT_PASSWORD,
    full_name: str | None = None,
    status: UserStatus = UserStatus.active,
) -> dict:
    """Insert a user straight into the database and return its API-ish dict."""
    db = SessionLocal()
    try:
        user = User(
            external_id=f"{role.value.upper()}-{uuid4().hex[:8]}",
            username=username,
            full_name=full_name or f"Test {role.value.title()}",
            email=email,
            password_hash=hash_password(password),
            role=role,
            status=status,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "id": str(user.id),
            "external_id": user.external_id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.value,
            "status": user.status.value,
        }
    finally:
        db.close()


def provision_from_payload(payload: dict, status: str = "active") -> dict:
    """Provision a non-voter account described by a test registration payload.

    Lets each module's register_user() helper keep its signature and call sites
    while routing organizer/system_admin around the now voter-only public route.
    """
    return create_user_directly(
        UserRole(payload["role"]),
        username=payload["username"],
        email=payload["email"],
        password=payload["password"],
        full_name=payload.get("full_name"),
        status=UserStatus(status),
    )


def create_organizer(suffix: str | None = None, password: str = DEFAULT_PASSWORD) -> dict:
    """Provision an organizer for tests that just need one to exist."""
    suffix = suffix or uuid4().hex[:8]

    return create_user_directly(
        UserRole.organizer,
        username=f"organizer_{suffix}",
        email=f"organizer_{suffix}@test.com",
        password=password,
    )


def create_system_admin(suffix: str | None = None, password: str = DEFAULT_PASSWORD) -> dict:
    """Provision a system admin (never creatable through any public route)."""
    suffix = suffix or uuid4().hex[:8]

    return create_user_directly(
        UserRole.system_admin,
        username=f"admin_{suffix}",
        email=f"admin_{suffix}@test.com",
        password=password,
    )
