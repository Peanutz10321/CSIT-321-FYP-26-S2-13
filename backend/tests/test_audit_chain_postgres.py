"""
Audit-chain concurrency tests. PostgreSQL only.

The chain is appended under a row lock on audit_chain_head (see
app/security/audit.py). SQLite cannot exercise that: SQLAlchemy omits FOR UPDATE
on that dialect and SQLite serialises writers itself, so a passing SQLite test
would prove nothing about the lock.

What matters here is that genuinely concurrent writers cannot both claim the same
position. Without the lock two transactions would read the same head, compute the
same sequence_number, and either collide on the unique constraint or fork the
chain. Every worker starts from a barrier so the contention is real rather than
incidental.

Setup command is in tests/test_migrations_postgres.py; these tests additionally
need ALLOW_DESTRUCTIVE_DB_TESTS=true.
"""

import os
import threading
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

from app.models.audit_log import AuditChainHead, AuditLog
from app.models.user import User, UserRole, UserStatus
from app.security.audit import CHAIN_ID, GENESIS_HASH, log_event, verify_audit_chain
from scripts.destructive_test_guard import require_safe_postgres_test_database


TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL is not set; see this module's docstring",
)

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Kept under the default SQLAlchemy pool (5 + 10 overflow) so the test measures
# lock contention rather than connection starvation.
WORKER_COUNT = 8
JOIN_TIMEOUT_SECONDS = 60


@pytest.fixture(scope="module")
def pg_sessionmaker():
    """A migrated PostgreSQL database and a sessionmaker bound to it."""
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
        yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def concurrent_append(pg_sessionmaker):
    """Append WORKER_COUNT events from WORKER_COUNT simultaneous transactions."""
    suffix = uuid.uuid4().hex[:8]

    db = pg_sessionmaker()
    try:
        actor = User(
            role=UserRole.voter,
            status=UserStatus.active,
            external_id=f"AUDIT-{suffix}",
            username=f"audit_actor_{suffix}",
            email=f"audit_actor_{suffix}@test.com",
            password_hash="not-a-real-hash",
        )
        db.add(actor)
        db.commit()
        actor_id = actor.id
    finally:
        db.close()

    barrier = threading.Barrier(WORKER_COUNT)
    outcomes: list[str | None] = [None] * WORKER_COUNT

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=JOIN_TIMEOUT_SECONDS)
        except threading.BrokenBarrierError:  # pragma: no cover - setup failure
            outcomes[index] = "barrier broken"
            return

        session = pg_sessionmaker()
        try:
            log_event(
                session,
                actor_user_id=actor_id,
                action="vote_cast",
                entity_type="ballot",
                details=f"worker={index}",
            )
            session.commit()
            outcomes[index] = "ok"
        except Exception as exc:  # noqa: BLE001 - recorded and asserted below
            session.rollback()
            outcomes[index] = f"{type(exc).__name__}: {exc}"
        finally:
            session.close()

    threads = [
        threading.Thread(target=worker, args=(index,), name=f"audit-worker-{index}")
        for index in range(WORKER_COUNT)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=JOIN_TIMEOUT_SECONDS)

    assert not any(thread.is_alive() for thread in threads), "a worker never finished"

    return outcomes


def test_every_concurrent_append_succeeds(concurrent_append):
    """No writer is lost, and none collides on the unique sequence number."""
    failures = [outcome for outcome in concurrent_append if outcome != "ok"]

    assert failures == []


def test_sequence_numbers_are_unique_and_contiguous(pg_sessionmaker, concurrent_append):
    db = pg_sessionmaker()
    try:
        sequence_numbers = [
            row.sequence_number
            for row in db.query(AuditLog).order_by(AuditLog.sequence_number).all()
        ]
    finally:
        db.close()

    assert len(sequence_numbers) == WORKER_COUNT
    assert len(set(sequence_numbers)) == WORKER_COUNT, "a position was claimed twice"
    assert sequence_numbers == list(range(1, WORKER_COUNT + 1))


def test_chain_verifies_after_concurrent_appends(pg_sessionmaker, concurrent_append):
    """The links must be intact, not merely the numbering."""
    db = pg_sessionmaker()
    try:
        result = verify_audit_chain(db)
    finally:
        db.close()

    assert result.ok, [problem.message for problem in result.problems]
    assert result.checked == WORKER_COUNT


def test_chain_head_matches_the_final_entry(pg_sessionmaker, concurrent_append):
    db = pg_sessionmaker()
    try:
        head = db.query(AuditChainHead).filter(AuditChainHead.id == CHAIN_ID).one()
        last = (
            db.query(AuditLog)
            .order_by(AuditLog.sequence_number.desc())
            .first()
        )

        assert head.sequence_number == WORKER_COUNT
        assert head.head_hash == last.entry_hash
        assert head.head_hash != GENESIS_HASH
    finally:
        db.close()
