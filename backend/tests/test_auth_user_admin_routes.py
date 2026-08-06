from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

from app.database import get_db
from app.main import app
from app.models.audit_log import AuditChainHead, AuditLog
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

    def with_for_update(self, *args, **kwargs):
        # Row locking has no meaning against an in-memory list; the audit chain
        # helper still calls it, so it has to be accepted and ignored.
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
        # Audited routes write through the same session, so the fake has to hold
        # the chain as well. Tests can assert on audit_logs directly.
        self.audit_logs = []
        self.chain_heads = []
        self.new = []

    def _collection_for(self, entity):
        if entity is AuditLog:
            return self.audit_logs
        if entity is AuditChainHead:
            return self.chain_heads
        return self.users

    def query(self, *entities):
        # query(User) yields entities; query(User.external_id) yields row tuples.
        entity = entities[0] if entities else None
        column = getattr(entity, "key", None)
        collection = self.users if column else self._collection_for(entity)
        return FakeQuery(collection, column=column)

    def add(self, obj):
        if isinstance(obj, (AuditLog, AuditChainHead)):
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
            self._collection_for(type(obj)).append(obj)
            self.new.append(obj)
            return

        if not obj.id:
            obj.id = uuid4()

        now = datetime.now(timezone.utc)

        if not obj.created_at:
            obj.created_at = now

        obj.updated_at = now

        self.users.append(obj)
        self.new.append(obj)

    def flush(self):
        for obj in self.new:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()
        self.new = []

    def commit(self):
        now = datetime.now(timezone.utc)
        for user in self.users:
            user.updated_at = now
        self.new = []

    def rollback(self):
        self.new = []

    def refresh(self, user):
        return user

    def close(self):
        pass

    def audit_actions(self):
        """Every audit action recorded through this session, in order."""
        return [entry.action for entry in self.audit_logs]


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


def test_public_organizer_registration_succeeds(client):
    """Policy reversal: organizers may again register publicly."""
    response = client.post(
        "/auth/register",
        json={
            "username": "organizer_rt",
            "email": "organizer_rt@test.com",
            "password": "password123",
            "role": "organizer",
        },
    )

    assert response.status_code == 201, response.text

    data = response.json()
    assert data["role"] == "organizer"
    assert data["status"] == "active"
    assert data["external_id"].startswith("ORG-")
    assert data["email"] == "organizer_rt@test.com"
    assert "password" not in data
    assert "password_hash" not in data


def test_registered_organizer_can_log_in_with_an_organizer_token(client):
    """The self-registered organizer authenticates and carries the organizer role."""
    from app.security.jwt import decode_access_token

    register = client.post(
        "/auth/register",
        json={
            "username": "organizer_login",
            "email": "organizer_login@test.com",
            "password": "password123",
            "role": "organizer",
        },
    )
    assert register.status_code == 201, register.text

    login_response = login(client, email="organizer_login@test.com")
    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]
    claims = decode_access_token(token)
    assert claims is not None
    assert claims["role"] == "organizer"


def test_public_organizer_registration_emits_one_organizer_created_event(client, fake_db):
    """The organizer_created audit event now fires on public registration."""
    response = client.post(
        "/auth/register",
        json={
            "username": "audited_org",
            "email": "audited_org@test.com",
            "password": "password123",
            "role": "organizer",
        },
    )
    assert response.status_code == 201, response.text
    organizer_id = response.json()["id"]

    assert fake_db.audit_actions() == ["organizer_created"]

    entry = fake_db.audit_logs[0]
    assert entry.action == "organizer_created"
    assert entry.entity_type == "user"
    assert str(entry.entity_id) == organizer_id
    # The new organizer is the actor of their own creation event.
    assert str(entry.actor_user_id) == organizer_id
    assert entry.details == '{"role":"organizer"}'


def test_organizer_registration_audit_holds_no_credentials(client, fake_db):
    """The event must identify the organizer but never carry credentials."""
    email = "no_creds_org@test.com"
    username = "no_creds_org"
    password = "super-secret-pw"

    response = client.post(
        "/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "role": "organizer",
        },
    )
    assert response.status_code == 201, response.text

    details = fake_db.audit_logs[0].details
    assert email not in details
    assert username not in details
    assert password not in details


def test_voter_registration_emits_no_audit_event(client, fake_db):
    """Only organizer creation is audited; a routine voter signup is not."""
    response = register_voter(client)

    assert response.status_code == 201, response.text
    assert fake_db.audit_actions() == []


def test_register_short_password_is_rejected(client):
    """Public registration must not weaken the previous 8-char minimum."""
    response = client.post(
        "/auth/register",
        json={
            "username": "shortpw",
            "email": "shortpw@test.com",
            "password": "short",
            "role": "voter",
        },
    )

    assert response.status_code == 422


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
    # Duplicate email and duplicate username answer identically so the endpoint
    # cannot be used to discover which accounts exist.
    assert "already exists" in response.json()["detail"].lower()


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


def test_admin_can_change_own_status(client, fake_db):
    """Self-status changes are allowed server-side.

    The UI never offers this path: an admin's own row is filtered out of the
    user list, and the status toggle is hidden when the target is the current
    user. It is reachable only by calling the API directly.
    """
    admin, token = _admin_token(client, fake_db)

    response = client.patch(f"/admin/users/{admin.id}/suspend", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["status"] == "suspended"

# ---------------------------------------------------------------------------
# The admin-only organizer provisioning endpoint has been removed
#
# Policy reversal: organizers self-register publicly again, so the product path
# POST /admin/users/organizers no longer exists. Admin user management keeps only
# list/search/view/status/suspend/unsuspend (covered above).
# ---------------------------------------------------------------------------

ORGANIZER_PAYLOAD = {
    "username": "new_organizer",
    "email": "new_organizer@test.com",
    "password": "password123",
    "full_name": "New Organizer",
}


def test_admin_organizer_provisioning_endpoint_is_gone(client, fake_db):
    """Even with a system admin authenticated, the endpoint must not exist."""
    _, token = _admin_token(client, fake_db)

    response = client.post(
        "/admin/users/organizers",
        json=ORGANIZER_PAYLOAD,
        headers=auth_headers(token),
    )

    # 404 (no such path) or 405 (path shape matches another method) — either way
    # the provisioning product path is unavailable, and nothing was created.
    assert response.status_code in (404, 405)
    assert all(user.role != UserRole.organizer for user in fake_db.users)


def test_register_trims_whitespace_around_username_and_email(client):
    response = client.post(
        "/auth/register",
        json={
            "username": "  padded  ",
            "email": "  padded@test.com  ",
            "password": "password123",
            "role": "voter",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "padded"
    assert body["email"] == "padded@test.com"


def test_register_padded_username_cannot_duplicate_an_existing_account(client):
    register_voter(client)

    # The uniqueness queries are exact matches, so an untrimmed "  voter  " would
    # slip past them and create a second, visually identical account.
    response = client.post(
        "/auth/register",
        json={
            "username": "  voter  ",
            "email": "different@test.com",
            "password": "password123",
            "role": "voter",
        },
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_register_padded_email_cannot_duplicate_an_existing_account(client):
    register_voter(client)

    response = client.post(
        "/auth/register",
        json={
            "username": "different",
            "email": "  voter@test.com  ",
            "password": "password123",
            "role": "voter",
        },
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_register_rejects_a_whitespace_only_username(client):
    response = client.post(
        "/auth/register",
        json={
            "username": "   ",
            "email": "spacey@test.com",
            "password": "password123",
            "role": "voter",
        },
    )

    assert response.status_code == 400
    assert "missing field" in response.json()["detail"].lower()


def test_update_trims_whitespace_around_the_username(client):
    register_voter(client)
    token = login(client).json()["access_token"]

    response = client.put(
        "/users/me",
        headers=auth_headers(token),
        json={"username": "  renamed  ", "email": "voter@test.com"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "renamed"


def test_update_rejects_a_whitespace_only_username(client):
    register_voter(client)
    token = login(client).json()["access_token"]

    # min_length=1 on the schema counts the spaces, so only the route can catch it.
    response = client.put(
        "/users/me",
        headers=auth_headers(token),
        json={"username": "   ", "email": "voter@test.com"},
    )

    assert response.status_code == 400
    assert "missing field" in response.json()["detail"].lower()


def test_update_padded_username_cannot_duplicate_another_account(client):
    register_voter(client)
    client.post(
        "/auth/register",
        json={
            "username": "taken",
            "email": "taken@test.com",
            "password": "password123",
            "role": "voter",
        },
    )
    token = login(client).json()["access_token"]

    response = client.put(
        "/users/me",
        headers=auth_headers(token),
        json={"username": "  taken  ", "email": "voter@test.com"},
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()
