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
    def __init__(self, users, column=None):
        self.users = users
        self.filters = []
        # Set when the caller queried a single column (e.g. query(User.external_id)),
        # which SQLAlchemy returns as row tuples rather than entities.
        self.column = column

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

    def _as_row(self, user):
        return (getattr(user, self.column),) if self.column else user

    def first(self):
        results = self._filtered_users()
        return self._as_row(results[0]) if results else None

    def all(self):
        return [self._as_row(user) for user in self._filtered_users()]

    def count(self):
        return len(self._filtered_users())


class FakeSession:
    def __init__(self):
        self.users = []

    def query(self, *entities):
        # query(User) yields entities; query(User.external_id) yields row tuples.
        column = getattr(entities[0], "key", None) if entities else None
        return FakeQuery(self.users, column=column)

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


def test_register_accepts_voter_role(client):
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


def test_public_organizer_registration_is_rejected(client, fake_db):
    """Organizer is a trusted role and must not be self-assignable."""
    response = client.post(
        "/auth/register",
        json={
            "username": "organizer_rt",
            "email": "organizer_rt@test.com",
            "password": "password123",
            "role": "organizer",
        },
    )

    assert response.status_code == 403
    assert "organizer" in response.json()["detail"].lower()
    # Nothing was created.
    assert fake_db.users == []


def test_register_defaults_to_voter_when_role_is_omitted(client):
    response = client.post(
        "/auth/register",
        json={
            "username": "no_role",
            "email": "no_role@test.com",
            "password": "password123",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "voter"


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

# ---------------------------------------------------------------------------
# Admin-only organizer provisioning
#
# Organizer is a trusted role (election creation, tally triggering), so it is
# rejected on the public registration route and can only be created here.
# ---------------------------------------------------------------------------

ORGANIZER_PAYLOAD = {
    "username": "new_organizer",
    "email": "new_organizer@test.com",
    "password": "password123",
    "full_name": "New Organizer",
}


def _create_organizer(client, token, **overrides):
    return client.post(
        "/admin/users/organizers",
        json={**ORGANIZER_PAYLOAD, **overrides},
        headers=auth_headers(token),
    )


def test_admin_can_create_an_organizer(client, fake_db):
    _, token = _admin_token(client, fake_db)

    response = _create_organizer(client, token)

    assert response.status_code == 201, response.text

    data = response.json()
    assert data["role"] == "organizer"
    assert data["status"] == "active"
    assert data["email"] == "new_organizer@test.com"
    assert data["full_name"] == "New Organizer"
    assert data["external_id"].startswith("ORG-")
    assert "password" not in data
    assert "password_hash" not in data


def test_admin_created_organizer_can_log_in(client, fake_db):
    _, token = _admin_token(client, fake_db)
    _create_organizer(client, token)

    response = login(client, email="new_organizer@test.com", password="password123")

    assert response.status_code == 200, response.text


def test_organizer_external_ids_are_sequential(client, fake_db):
    _, token = _admin_token(client, fake_db)

    first = _create_organizer(client, token)
    second = _create_organizer(
        client,
        token,
        username="second_organizer",
        email="second_organizer@test.com",
    )

    assert first.json()["external_id"] == "ORG-001"
    assert second.json()["external_id"] == "ORG-002"


def test_creating_organizer_generates_full_name_when_omitted(client, fake_db):
    _, token = _admin_token(client, fake_db)

    response = _create_organizer(client, token, full_name=None)

    assert response.status_code == 201, response.text
    assert response.json()["full_name"]


def test_creating_organizer_rejects_duplicate_email(client, fake_db):
    _, token = _admin_token(client, fake_db)
    _create_organizer(client, token)

    response = _create_organizer(client, token, username="different_username")

    assert response.status_code == 400
    assert response.json()["detail"] == "Account already exists."


def test_creating_organizer_rejects_duplicate_username(client, fake_db):
    _, token = _admin_token(client, fake_db)
    _create_organizer(client, token)

    response = _create_organizer(client, token, email="different@test.com")

    assert response.status_code == 400
    assert response.json()["detail"] == "Username already exists."


def test_creating_organizer_rejects_short_password(client, fake_db):
    _, token = _admin_token(client, fake_db)

    response = _create_organizer(client, token, password="short")

    assert response.status_code == 422


def test_voter_cannot_create_an_organizer(client, fake_db):
    voter = make_user(
        role=UserRole.voter,
        external_id="VOTER-001",
        username="plain_voter",
        email="plain_voter@test.com",
        password="password123",
    )
    fake_db.users.append(voter)
    token = login(client, email="plain_voter@test.com", password="password123").json()[
        "access_token"
    ]

    response = _create_organizer(client, token)

    assert response.status_code == 403
    assert response.json()["detail"] == "System admin access required"
    assert all(user.role != UserRole.organizer for user in fake_db.users)


def test_organizer_cannot_create_another_organizer(client, fake_db):
    """No privilege escalation: organizers cannot mint more organizers."""
    organizer = make_user(
        role=UserRole.organizer,
        external_id="ORG-001",
        username="existing_organizer",
        email="existing_organizer@test.com",
        password="password123",
    )
    fake_db.users.append(organizer)
    token = login(
        client, email="existing_organizer@test.com", password="password123"
    ).json()["access_token"]

    response = _create_organizer(client, token)

    assert response.status_code == 403
    assert response.json()["detail"] == "System admin access required"
    assert len([u for u in fake_db.users if u.role == UserRole.organizer]) == 1


def test_creating_organizer_requires_authentication(client, fake_db):
    response = client.post("/admin/users/organizers", json=ORGANIZER_PAYLOAD)

    # 401: no bearer credentials supplied at all.
    assert response.status_code == 401
    assert fake_db.users == []


def test_suspended_admin_cannot_create_an_organizer(client, fake_db):
    admin, token = _admin_token(client, fake_db)
    admin.status = UserStatus.suspended

    response = _create_organizer(client, token)

    assert response.status_code == 403
