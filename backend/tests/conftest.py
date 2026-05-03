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


@pytest.fixture(autouse=True)
def clean_test_records():
    yield

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("""
            DELETE FROM audit_logs
            WHERE actor_user_id IN (
                SELECT id FROM users WHERE email ILIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM candidate_results
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.teacher_id
                WHERE u.email ILIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM ballots
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.teacher_id
                WHERE u.email ILIKE '%@test.com'
            )
            OR election_voter_id IN (
                SELECT ev.id
                FROM election_voters ev
                JOIN users u ON u.id = ev.student_id
                WHERE u.email ILIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM election_voters
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.teacher_id
                WHERE u.email ILIKE '%@test.com'
            )
            OR student_id IN (
                SELECT id FROM users WHERE email ILIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM candidates
            WHERE election_id IN (
                SELECT e.id
                FROM elections e
                JOIN users u ON u.id = e.teacher_id
                WHERE u.email ILIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM elections
            WHERE teacher_id IN (
                SELECT id FROM users WHERE email ILIKE '%@test.com'
            )
        """))

        db.execute(text("""
            DELETE FROM users
            WHERE email ILIKE '%@test.com'
        """))

        db.commit()
    finally:
        db.close()