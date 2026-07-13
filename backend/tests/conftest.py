import os

from dotenv import load_dotenv
import pytest
from sqlalchemy import text


os.environ["APP_ENV"] = "test"
load_dotenv(".env.test", override=True)


def _is_truthy(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "yes", "y"}


def pytest_configure(config):
    if os.getenv("APP_ENV") != "test" or not _is_truthy(os.getenv("TESTING")):
        raise RuntimeError(
            "Refusing to run tests because APP_ENV=test and TESTING=true were not loaded. "
            "Create backend/.env.test from .env.test.example and run pytest again."
        )

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from .env.test")

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

    from app.database import SessionLocal

    db = SessionLocal()
    try:
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