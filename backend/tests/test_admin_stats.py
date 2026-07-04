"""
Contract test for the admin stats endpoint.

Guards the terminology rename of the AdminStatsResponse fields
(total_students/total_teachers -> total_voters/total_organizers) so the
new keys can't silently regress and break the admin dashboard.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.user import User, UserRole, UserStatus
from app.security.password import hash_password


client = TestClient(app)


def _create_system_admin() -> str:
    suffix = uuid4().hex[:8]
    email = f"admin_{suffix}@test.com"

    db = SessionLocal()
    try:
        admin = User(
            id=uuid4(),
            role=UserRole.system_admin,
            status=UserStatus.active,
            external_id=f"ADM-{suffix}",
            username=f"admin_{suffix}",
            full_name="Stats Admin",
            email=email,
            password_hash=hash_password("testing123"),
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()

    return email


def _login(email: str, password: str = "testing123") -> str:
    response = client.post(
        f"/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_admin_stats_uses_new_role_terminology_keys():
    email = _create_system_admin()
    token = _login(email)

    response = client.get(
        "/admin/stats",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text

    data = response.json()

    # New flexible e-voting keys must be present.
    assert "total_voters" in data
    assert "total_organizers" in data
    assert "total_admins" in data

    # Old school-specific keys must be gone.
    assert "total_students" not in data
    assert "total_teachers" not in data
