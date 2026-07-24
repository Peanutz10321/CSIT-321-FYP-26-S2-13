import os

from dotenv import load_dotenv
import pytest
from sqlalchemy import text


os.environ["APP_ENV"] = "test"
load_dotenv(".env.test", override=True)


def _is_truthy(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "yes", "y"}


def _require_safe_test_target(database_url: str) -> None:
    """Refuse to run the suite against a database it may not delete from.

    The clean_test_records fixture below issues DELETE statements against
    DATABASE_URL after every test. They are scoped to %@test.com accounts, so the
    blast radius is bounded, but pointing DATABASE_URL at a shared or deployed
    database would still remove real rows. SQLite is always allowed because the
    test database is a throwaway local file; anything else has to be named
    explicitly.
    """
    from sqlalchemy.engine import make_url

    url = make_url(database_url)

    if url.get_backend_name() == "sqlite":
        return

    allowed = {
        name.strip().lower()
        for name in os.getenv("ALLOWED_TEST_DATABASES", "").split(",")
        if name.strip()
    }

    if (url.database or "").lower() not in allowed:
        raise RuntimeError(
            "Refusing to run the test suite against a non-SQLite DATABASE_URL "
            "that is not listed in ALLOWED_TEST_DATABASES. The per-test cleanup "
            "deletes rows, so the target must be named explicitly."
        )


def pytest_configure(config):
    if os.getenv("APP_ENV") != "test" or not _is_truthy(os.getenv("TESTING")):
        raise RuntimeError(
            "Refusing to run tests because APP_ENV=test and TESTING=true were not loaded. "
            "Create backend/.env.test from .env.test.example and run pytest again."
        )

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from .env.test")

    _require_safe_test_target(database_url)

    import app.models.user
    import app.models.election
    import app.models.election_key
    import app.models.candidate
    import app.models.election_voter
    import app.models.ballot
    import app.models.candidate_result
    import app.models.audit_log

    from app.database import Base, engine

    # For the throwaway SQLite test database, rebuild the schema from scratch on
    # every run so stale tables can never mask a model change. Never drop tables
    # on a server database (e.g. Postgres).
    if engine.dialect.name == "sqlite":
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_test_records():
    yield

    from app.database import SessionLocal, engine

    is_sqlite = engine.dialect.name == "sqlite"

    db = SessionLocal()
    try:
        if is_sqlite:
            # The SQLite test database is disposable, so the audit trail and its
            # chain head are reset together: the whole log is cleared and the head
            # removed, leaving the next test an intact chain from genesis. A scoped
            # delete that removed only some rows would leave the head pointing at a
            # deleted entry, which is exactly the "truncated"/"missing" condition
            # verify_audit_chain reports — a broken harness, not a broken chain.
            db.execute(text("DELETE FROM audit_logs"))
            db.execute(text("DELETE FROM audit_chain_head"))
        else:
            # Non-SQLite is never the target of this cleanup in the suite (the
            # PostgreSQL tests manage their own databases). Keep the historical
            # scoped delete for safety rather than wiping a server-side table.
            db.execute(text("""
                DELETE FROM audit_logs
                WHERE actor_user_id IN (
                    SELECT id FROM users WHERE email LIKE '%@test.com'
                )
            """))

        db.execute(text("""
            DELETE FROM candidate_results
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.organizer_id
                WHERE u.email LIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM ballots
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.organizer_id
                WHERE u.email LIKE '%@test.com'
            )
            OR election_voter_id IN (
                SELECT ev.id
                FROM election_voters ev
                JOIN users u ON u.id = ev.voter_id
                WHERE u.email LIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM election_voters
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.organizer_id
                WHERE u.email LIKE '%@test.com'
            )
            OR voter_id IN (
                SELECT id FROM users WHERE email LIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM candidates
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.organizer_id
                WHERE u.email LIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM election_keys
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.organizer_id
                WHERE u.email LIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM elections
            WHERE organizer_id IN (
                SELECT id FROM users WHERE email LIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM users
            WHERE email LIKE '%@test.com'
        """))

        db.commit()
    finally:
        db.close()