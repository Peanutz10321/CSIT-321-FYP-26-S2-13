"""
Effective audit-permission tests. PostgreSQL only.

These prove the verifier reports the right answer for a correctly-restricted
application role, for over-privileged roles, and for the owner. ``SET ROLE`` is
used to evaluate ``has_table_privilege`` as a dedicated non-owner role without
opening a second connection.

They run only against the guarded throwaway test database (never Supabase or any
shared database) and need ALLOW_DESTRUCTIVE_DB_TESTS=true, because the module
rebuilds the public schema. Setup command is in tests/test_migrations_postgres.py.
"""

import os
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from scripts.destructive_test_guard import require_safe_postgres_test_database
from scripts.verify_audit_permissions import check_effective_privileges


TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL is not set; see this module's docstring",
)

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def migrated_engine():
    """A throwaway PostgreSQL database migrated to head (audit tables present)."""
    require_safe_postgres_test_database(
        TEST_POSTGRES_URL,
        destructive_tests_allowed=os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS"),
    )

    engine = sa.create_engine(TEST_POSTGRES_URL)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))

    config = Config(os.path.join(BACKEND_ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_ROOT, "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_POSTGRES_URL)
    command.upgrade(config, "head")

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def app_role(migrated_engine):
    """A dedicated non-owner role, dropped again after the test."""
    role = f"evoting_app_{uuid.uuid4().hex[:8]}"

    with migrated_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE ROLE "{role}" NOLOGIN'))
        # The harness recreates schema public with CREATE SCHEMA, which — unlike
        # the initdb public schema — grants USAGE to nobody. Without schema USAGE
        # the role cannot resolve the tables at all (they read as "does not
        # exist"), which is orthogonal to the table privileges under test. A real
        # application role has this; grant it here so the test measures the right
        # thing.
        connection.execute(sa.text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))

    try:
        yield role
    finally:
        with migrated_engine.begin() as connection:
            connection.execute(sa.text(f'DROP OWNED BY "{role}"'))
            connection.execute(sa.text(f'DROP ROLE IF EXISTS "{role}"'))


def _grant(engine, sql: str) -> None:
    with engine.begin() as connection:
        connection.execute(sa.text(sql))


def _problems_as_role(engine, role: str):
    """Effective-privilege problems evaluated while acting as `role`."""
    with engine.connect() as connection:
        connection.execute(sa.text(f'SET ROLE "{role}"'))
        try:
            return check_effective_privileges(connection)
        finally:
            connection.execute(sa.text("RESET ROLE"))


def test_correctly_restricted_role_passes(migrated_engine, app_role):
    _grant(migrated_engine, f'GRANT INSERT, SELECT ON public.audit_logs TO "{app_role}"')
    _grant(
        migrated_engine,
        f'GRANT SELECT, INSERT, UPDATE ON public.audit_chain_head TO "{app_role}"',
    )

    problems = _problems_as_role(migrated_engine, app_role)

    assert problems == [], [str(p) for p in problems]


def test_role_with_update_on_audit_logs_is_flagged(migrated_engine, app_role):
    _grant(
        migrated_engine,
        f'GRANT INSERT, SELECT, UPDATE ON public.audit_logs TO "{app_role}"',
    )
    _grant(
        migrated_engine,
        f'GRANT SELECT, INSERT, UPDATE ON public.audit_chain_head TO "{app_role}"',
    )

    problems = _problems_as_role(migrated_engine, app_role)

    assert any(
        p.table == "public.audit_logs" and p.privilege == "UPDATE" for p in problems
    ), [str(p) for p in problems]


def test_role_with_delete_on_audit_logs_is_flagged(migrated_engine, app_role):
    _grant(
        migrated_engine,
        f'GRANT INSERT, SELECT, DELETE ON public.audit_logs TO "{app_role}"',
    )
    _grant(
        migrated_engine,
        f'GRANT SELECT, INSERT, UPDATE ON public.audit_chain_head TO "{app_role}"',
    )

    problems = _problems_as_role(migrated_engine, app_role)

    assert any(
        p.table == "public.audit_logs" and p.privilege == "DELETE" for p in problems
    ), [str(p) for p in problems]


def test_role_missing_insert_is_flagged(migrated_engine, app_role):
    """Only SELECT granted: the append path is broken and must be reported."""
    _grant(migrated_engine, f'GRANT SELECT ON public.audit_logs TO "{app_role}"')
    _grant(
        migrated_engine,
        f'GRANT SELECT, INSERT, UPDATE ON public.audit_chain_head TO "{app_role}"',
    )

    problems = _problems_as_role(migrated_engine, app_role)

    assert any(
        p.table == "public.audit_logs" and p.privilege == "INSERT" and p.expected is True
        for p in problems
    ), [str(p) for p in problems]


def test_owner_role_is_flagged(migrated_engine):
    """The database owner implicitly holds every privilege, so it must fail.

    This is the misconfiguration the docs warn about: revoking from an owner does
    nothing. The connecting superuser owns the tables here, so the deny checks
    must report violations.
    """
    with migrated_engine.connect() as connection:
        problems = check_effective_privileges(connection)

    denied_but_allowed = [p for p in problems if p.expected is False and p.actual is True]
    assert denied_but_allowed, [str(p) for p in problems]


def test_verification_does_not_change_privileges(migrated_engine, app_role):
    """The verifier is read-only: running it must not alter the role's grants."""
    _grant(migrated_engine, f'GRANT INSERT, SELECT ON public.audit_logs TO "{app_role}"')
    _grant(
        migrated_engine,
        f'GRANT SELECT, INSERT, UPDATE ON public.audit_chain_head TO "{app_role}"',
    )

    before = _problems_as_role(migrated_engine, app_role)
    _problems_as_role(migrated_engine, app_role)  # run again
    after = _problems_as_role(migrated_engine, app_role)

    assert [str(p) for p in before] == [str(p) for p in after] == []


# ---------------------------------------------------------------------------
# Operation-level evidence
#
# has_table_privilege reports what the catalog says; these prove PostgreSQL
# actually enforces it. The role connects for real (LOGIN) and each expected
# failure runs in its own transaction, because a permission error aborts the
# current one.
# ---------------------------------------------------------------------------


import hashlib  # noqa: E402


def _attempt(engine, sql, params=None):
    """Run one statement in its own transaction.

    Returns None on success, or the raised exception. Isolated per call so a
    permission error (which aborts the transaction) cannot affect later checks.
    """
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(sql), params or {})
        return None
    except Exception as exc:  # noqa: BLE001 - inspected by the caller
        return exc


def _is_permission_denied(exc) -> bool:
    return exc is not None and "permission denied" in str(exc).lower()


@pytest.fixture
def restricted_runtime(migrated_engine):
    """A LOGIN runtime role restricted per policy, plus an engine bound to it and
    an owner-created actor user id the role can reference in an INSERT."""
    suffix = uuid.uuid4().hex[:8]
    role = f"evoting_rt_{suffix}"
    password = "rt-test-password"
    actor_id = uuid.uuid4()

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(f'CREATE ROLE "{role}" LOGIN PASSWORD :pw'), {"pw": password}
        )
        connection.execute(sa.text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
        connection.execute(
            sa.text(f'GRANT INSERT, SELECT ON public.audit_logs TO "{role}"')
        )
        connection.execute(
            sa.text(
                f'GRANT SELECT, INSERT, UPDATE ON public.audit_chain_head TO "{role}"'
            )
        )
        # Owner-created prerequisite: audit_logs.actor_user_id is a NOT NULL FK to
        # users, so a valid INSERT needs an existing user to point at. The module
        # database is not reset between these tests, so the identifiers are unique
        # per role to avoid colliding with a previous test's actor.
        connection.execute(
            sa.text(
                "INSERT INTO users (id, role, status, external_id, username, "
                "email, password_hash) VALUES (:id, 'voter', 'active', "
                ":external_id, :username, :email, 'x')"
            ),
            {
                "id": actor_id,
                "external_id": f"PERM-{suffix}",
                "username": f"perm_actor_{suffix}",
                "email": f"perm_actor_{suffix}@test.com",
            },
        )

    role_engine = sa.create_engine(
        sa.engine.make_url(TEST_POSTGRES_URL).set(username=role, password=password)
    )
    try:
        yield role_engine, actor_id
    finally:
        role_engine.dispose()
        with migrated_engine.begin() as connection:
            connection.execute(sa.text(f'DROP OWNED BY "{role}"'))
            connection.execute(sa.text(f'DROP ROLE IF EXISTS "{role}"'))


def _valid_audit_insert(actor_id):
    """A structurally valid audit_logs INSERT far past any existing sequence."""
    sequence_number = 900000 + uuid.uuid4().int % 90000
    entry_hash = hashlib.sha256(str(sequence_number).encode()).hexdigest()
    return (
        "INSERT INTO audit_logs (id, actor_user_id, action, entity_type, "
        "sequence_number, previous_hash, entry_hash, created_at) VALUES "
        "(:id, :actor, 'vote_cast', 'election', :seq, :prev, :hash, now())",
        {
            "id": uuid.uuid4(),
            "actor": actor_id,
            "seq": sequence_number,
            "prev": "0" * 64,
            "hash": entry_hash,
        },
    )


class TestAuditLogsOperations:
    def test_select_succeeds(self, restricted_runtime):
        engine, _ = restricted_runtime
        assert _attempt(engine, "SELECT count(*) FROM audit_logs") is None

    def test_insert_succeeds(self, restricted_runtime):
        engine, actor_id = restricted_runtime
        sql, params = _valid_audit_insert(actor_id)
        assert _attempt(engine, sql, params) is None

    def test_update_is_rejected(self, restricted_runtime):
        engine, _ = restricted_runtime
        exc = _attempt(engine, "UPDATE audit_logs SET action = 'tampered'")
        assert _is_permission_denied(exc), exc

    def test_delete_is_rejected(self, restricted_runtime):
        engine, _ = restricted_runtime
        exc = _attempt(engine, "DELETE FROM audit_logs")
        assert _is_permission_denied(exc), exc

    def test_truncate_is_rejected(self, restricted_runtime):
        engine, _ = restricted_runtime
        exc = _attempt(engine, "TRUNCATE audit_logs")
        assert _is_permission_denied(exc), exc


class TestAuditChainHeadOperations:
    def test_update_succeeds(self, restricted_runtime):
        """The append path rewrites the head, so UPDATE must be allowed."""
        engine, _ = restricted_runtime
        exc = _attempt(
            engine,
            "UPDATE audit_chain_head SET updated_at = now() WHERE id = 'global'",
        )
        assert exc is None, exc

    def test_delete_is_rejected(self, restricted_runtime):
        engine, _ = restricted_runtime
        exc = _attempt(engine, "DELETE FROM audit_chain_head")
        assert _is_permission_denied(exc), exc

    def test_truncate_is_rejected(self, restricted_runtime):
        engine, _ = restricted_runtime
        exc = _attempt(engine, "TRUNCATE audit_chain_head")
        assert _is_permission_denied(exc), exc
