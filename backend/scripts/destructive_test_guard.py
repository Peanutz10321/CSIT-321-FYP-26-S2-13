"""Fail closed before destructive PostgreSQL integration-test setup."""

from sqlalchemy.engine import make_url


_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}
_REQUIRED_DATABASE = "evoting_test"


def require_safe_postgres_test_database(
    db_url: str | None,
    *,
    destructive_tests_allowed: str | None,
) -> None:
    """Reject any target that is not the explicitly approved local test DB."""
    if not db_url:
        raise RuntimeError("TEST_POSTGRES_URL must be set before destructive tests run")

    if str(destructive_tests_allowed).lower() != "true":
        raise RuntimeError(
            "Refusing destructive database tests unless "
            "ALLOW_DESTRUCTIVE_DB_TESTS=true is explicitly set"
        )

    url = make_url(db_url)

    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Destructive migration tests require a PostgreSQL database")

    if (url.host or "").lower() not in _ALLOWED_HOSTS:
        raise RuntimeError(
            "Refusing destructive migration tests against a non-localhost database"
        )

    if url.database != _REQUIRED_DATABASE:
        raise RuntimeError(
            f"Refusing destructive migration tests unless the database is "
            f"'{_REQUIRED_DATABASE}'"
        )
