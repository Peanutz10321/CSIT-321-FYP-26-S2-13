"""Unit tests for the destructive PostgreSQL-test database guard."""

import pytest

from scripts.destructive_test_guard import require_safe_postgres_test_database


@pytest.mark.parametrize(
    "db_url",
    [
        "postgresql://postgres:postgres@localhost:5432/evoting_test",
        "postgresql://postgres:postgres@127.0.0.1:5432/evoting_test",
        "postgresql://postgres:postgres@[::1]:5432/evoting_test",
    ],
)
def test_guard_accepts_explicitly_allowed_local_test_database(db_url):
    require_safe_postgres_test_database(
        db_url,
        destructive_tests_allowed="true",
    )


def test_guard_rejects_missing_explicit_opt_in():
    with pytest.raises(RuntimeError, match="ALLOW_DESTRUCTIVE_DB_TESTS=true"):
        require_safe_postgres_test_database(
            "postgresql://postgres:postgres@localhost:5432/evoting_test",
            destructive_tests_allowed=None,
        )


def test_guard_rejects_non_postgresql_database():
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        require_safe_postgres_test_database(
            "sqlite:///evoting_test.db",
            destructive_tests_allowed="true",
        )


def test_guard_rejects_remote_host():
    with pytest.raises(RuntimeError, match="localhost"):
        require_safe_postgres_test_database(
            "postgresql://postgres:postgres@db.example.supabase.co:5432/evoting_test",
            destructive_tests_allowed="true",
        )


def test_guard_rejects_wrong_database_name():
    with pytest.raises(RuntimeError, match="evoting_test"):
        require_safe_postgres_test_database(
            "postgresql://postgres:postgres@localhost:5432/postgres",
            destructive_tests_allowed="true",
        )


def test_guard_rejects_missing_database_url():
    with pytest.raises(RuntimeError, match="TEST_POSTGRES_URL"):
        require_safe_postgres_test_database(
            None,
            destructive_tests_allowed="true",
        )
