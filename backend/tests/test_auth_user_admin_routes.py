from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

from app.database import get_db
from app.main import app
from app.models.user import User, UserRole, UserStatus
from app.security.password import hash_password


def make_user(
    *,
    role=UserRole.voter,
    status=UserStatus.active,
    external_id="S1234567",
    username="voter",
    full_name="Voter User",
    email="voter@test.com",
    password="password123",
):
    now = datetime.now(timezone.utc)

    user = User(
        id=uuid4(),
        role=role,
        status=status,
        external_id=external_id,
        username=username,
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        created_at=now,
        updated_at=now,
    )

    return user


def get_column_name(expression: BinaryExpression):
    return expression.left.key


def get_expression_value(expression: BinaryExpression):
    return expression.right.value


def evaluate_expression(expression, user):
    if isinstance(expression, BooleanClauseList):
        if expression.operator == operators.or_:
            return any(evaluate_expression(clause, user) for clause in expression.clauses)
        return all(evaluate_expression(clause, user) for clause in expression.clauses)

    if isinstance(expression, BinaryExpression):
        column_name = get_column_name(expression)
        expected_value = get_expression_value(expression)
        actual_value = getattr(user, column_name)

        if expression.operator == operators.eq:
            return actual_value == expected_value

        if expression.operator == operators.ne:
            return actual_value != expected_value

        if expression.operator in [operators.like_op, operators.ilike_op]:
            keyword = str(expected_value).replace("%", "").lower()
            return keyword in str(actual_value).lower()

    return True


class FakeQuery:
    def __init__(self, users):
        self.users = users
        self.filters = []

    def filter(self, *expressions):
        self.filters.extend(expressions)
        return self

    def order_by(self, *args):
        return self

    def _filtered_users(self):
        results = self.users

        for expression in self.filters:
            results = [user for user in results if evaluate_expression(expression, user)]

        return results

    def first(self):
        results = self._filtered_users()
        return results[0] if results else None

    def all(self):
        return self._filtered_users()

    def count(self):
        return len(self._filtered_users())


class FakeSession:
    def __init__(self):
        self.users = []

    def query(self, model):
        return FakeQuery(self.users)

    def add(self, user):
        if not user.id:
            user.id = uuid4()

        now = datetime.now(timezone.utc)

        if not user.created_at:
            user.created_at = now

        user.updated_at = now

        self.users.append(user)

    def commit(self):
        now = datetime.now(timezone.utc)
        for user in self.users:
            user.updated_at = now

    def refresh(self, user):
        return user

    def close(self):
        pass


@pytest.fixture()
def fake_db():
    return FakeSession()


@pytest.fixture()
def client(fake_db):
    app.dependency_overrides[get_db] = lambda: fake_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def register_voter(client):
    return client.post(
        "/auth/register",
        json={
            "external_id": "S1234567",
            "username": "voter",
            "full_name": "Voter User",
            "email": "voter@test.com",
            "password": "password123",
            "role": "voter",
        },
    )


def login(client, email="voter@test.com", password="password123"):
    return client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_voter_success(client):
    response = register_voter(client)

    assert response.status_code == 201

    data = response.json()

    assert data["role"] == "voter"
    assert data["status"] == "active"
    assert data["email"] == "voter@test.com"
    assert "password" not in data
    assert "password_hash" not in data


def test_register_system_admin_is_rejected(client):
    response = client.post(
        "/auth/register",
        json={
            "external_id": "ADMIN001",
            "username": "admin",
            "full_name": "System Admin",
            "email": "admin@test.com",
            "password": "admin123",
            "role": "system_admin",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "System admin accounts cannot be registered publicly"


def test_register_accepts_voter_and_organizer_roles(client):
    voter = client.post(
        "/auth/register",
        json={
            "username": "voter_rt",
            "email": "voter_rt@test.com",
            "password": "password123",
            "role": "voter",
        },
    )
    assert voter.status_code == 201, voter.text
    assert voter.json()["role"] == "voter"

    organizer = client.post(
        "/auth/register",
        json={
            "username": "organizer_rt",
            "email": "organizer_rt@test.com",
            "password": "password123",
            "role": "organizer",
        },
    )
    assert organizer.status_code == 201, organizer.text
    assert organizer.json()["role"] == "organizer"


def test_register_rejects_legacy_student_role(client):
    """The old school-specific role strings must no longer be accepted."""
    response = client.post(
        "/auth/register",
        json={
            "username": "legacy_role",
            "email": "legacy_role@test.com",
            "password": "password123",
            "role": "student",
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "voter" in detail or "organizer" in detail


def test_generated_external_id_uses_role_prefix(client):
    voter = client.post(
        "/auth/register",
        json={
            "username": "prefix_voter",
            "email": "prefix_voter@test.com",
            "password": "password123",
            "role": "voter",
        },
    )
    assert voter.status_code == 201, voter.text
    assert voter.json()["external_id"].startswith("VOTER-")

    organizer = client.post(
        "/auth/register",
        json={
            "username": "prefix_organizer",
            "email": "prefix_organizer@test.com",
            "password": "password123",
            "role": "organizer",
        },
    )
    assert organizer.status_code == 201, organizer.text
    assert organizer.json()["external_id"].startswith("ORG-")


def test_login_success(client):
    register_voter(client)

    response = login(client)

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password_fails(client):
    register_voter(client)

    response = login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["detail"] == "Please provide a valid email and password"


def test_view_own_account(client):
    register_voter(client)
    login_response = login(client)
    token = login_response.json()["access_token"]

    response = client.get("/users/me", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["email"] == "voter@test.com"


def test_update_own_account_and_login_with_new_password(client):
    register_voter(client)
    login_response = login(client)
    token = login_response.json()["access_token"]

    update_response = client.put(
        "/users/me",
        headers=auth_headers(token),
        json={
            "username": "voter_updated",
            "full_name": "Voter Updated",
            "email": "voter_updated@test.com",
            "password": "newpass123",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["email"] == "voter_updated@test.com"

    old_password_response = login(
        client,
        email="voter_updated@test.com",
        password="password123",
    )
    assert old_password_response.status_code == 401

    new_password_response = login(
        client,
        email="voter_updated@test.com",
        password="newpass123",
    )
    assert new_password_response.status_code == 200


def test_voter_cannot_access_admin_routes(client):
    register_voter(client)
    login_response = login(client)
    token = login_response.json()["access_token"]

    response = client.get("/admin/users", headers=auth_headers(token))

    assert response.status_code == 403
    assert response.json()["detail"] == "System admin access required"


def test_admin_can_list_suspend_and_unsuspend_users(client, fake_db):
    voter = make_user(
        role=UserRole.voter,
        external_id="S1234567",
        username="voter",
        email="voter@test.com",
    )

    admin = make_user(
        role=UserRole.system_admin,
        external_id="ADMIN001",
        username="admin",
        full_name="System Admin",
        email="admin@test.com",
        password="admin123",
    )

    fake_db.users.extend([voter, admin])

    login_response = login(client, email="admin@test.com", password="admin123")
    admin_token = login_response.json()["access_token"]

    list_response = client.get("/admin/users", headers=auth_headers(admin_token))
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    suspend_response = client.patch(
        f"/admin/users/{voter.id}/suspend",
        headers=auth_headers(admin_token),
    )

    assert suspend_response.status_code == 200
    assert suspend_response.json()["status"] == "suspended"

    unsuspend_response = client.patch(
        f"/admin/users/{voter.id}/unsuspend",
        headers=auth_headers(admin_token),
    )

    assert unsuspend_response.status_code == 200
    assert unsuspend_response.json()["status"] == "active"


def test_register_duplicate_username_is_rejected(client):
    register_voter(client)

    response = client.post(
        "/auth/register",
        json={
            "username": "voter",
            "email": "different@test.com",
            "password": "password123",
            "role": "voter",
        },
    )

    assert response.status_code == 400
    assert "username" in response.json()["detail"].lower()


def _admin_token(client, fake_db):
    admin = make_user(
        role=UserRole.system_admin,
        external_id="ADMIN001",
        username="admin",
        full_name="System Admin",
        email="admin@test.com",
        password="admin123",
    )
    fake_db.users.append(admin)
    token = login(client, email="admin@test.com", password="admin123").json()["access_token"]
    return admin, token


def test_suspend_missing_user_returns_404(client, fake_db):
    _, token = _admin_token(client, fake_db)

    response = client.patch(f"/admin/users/{uuid4()}/suspend", headers=auth_headers(token))

    assert response.status_code == 404


def test_unsuspend_missing_user_returns_404(client, fake_db):
    _, token = _admin_token(client, fake_db)

    response = client.patch(f"/admin/users/{uuid4()}/unsuspend", headers=auth_headers(token))

    assert response.status_code == 404


def test_admin_cannot_suspend_self(client, fake_db):
    admin, token = _admin_token(client, fake_db)

    response = client.patch(f"/admin/users/{admin.id}/suspend", headers=auth_headers(token))

    assert response.status_code == 400