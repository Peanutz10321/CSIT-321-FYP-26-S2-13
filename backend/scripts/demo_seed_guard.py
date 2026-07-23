"""
Fail-closed guard for the demo seed script.

Seeding truncates every application table, so it must never run against a
database nobody intended. Four independent conditions must all hold:

1. DEMO_SEED_ALLOWED=true              - arms the script at all
2. the URL host is in DEMO_SEED_ALLOWED_HOSTS
3. the URL database is in DEMO_SEED_ALLOWED_DATABASES
4. --reset was passed                  - required before anything is truncated

Why the allowlist is configuration here, while the equivalent guard for the
PostgreSQL tests (scripts/destructive_test_guard.py) hardcodes its values: the
test target must never vary, so hardcoding is strictly safer there. The demo
target legitimately differs per environment (a local database, a shared demo
project), so hardcoding would either block real use or bake a deployment-specific
name into the repository. Both allowlists are therefore required and empty by
default - an unset variable refuses, it does not wave the run through.
"""

from sqlalchemy.engine import make_url


ALLOWED_FLAG = "DEMO_SEED_ALLOWED"
ALLOWED_HOSTS_VAR = "DEMO_SEED_ALLOWED_HOSTS"
ALLOWED_DATABASES_VAR = "DEMO_SEED_ALLOWED_DATABASES"
PASSWORD_VAR = "DEMO_SEED_PASSWORD"


def _parse_allowlist(raw: str | None) -> set[str]:
    """Split a comma-separated allowlist. Blank/unset yields an empty set."""
    if not raw:
        return set()

    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _is_true(value: str | None) -> bool:
    return str(value).lower() == "true"


def require_safe_demo_database(
    db_url: str | None,
    *,
    seed_allowed: str | None,
    allowed_hosts: str | None,
    allowed_databases: str | None,
) -> None:
    """Raise unless every condition for seeding this database is satisfied."""
    if not db_url:
        raise RuntimeError("DATABASE_URL must be set before seeding")

    if not _is_true(seed_allowed):
        raise RuntimeError(
            f"Refusing to seed unless {ALLOWED_FLAG}=true is explicitly set"
        )

    hosts = _parse_allowlist(allowed_hosts)
    if not hosts:
        raise RuntimeError(
            f"Refusing to seed: {ALLOWED_HOSTS_VAR} is not set. List the hosts "
            f"this database may be seeded on, e.g. {ALLOWED_HOSTS_VAR}=localhost"
        )

    databases = _parse_allowlist(allowed_databases)
    if not databases:
        raise RuntimeError(
            f"Refusing to seed: {ALLOWED_DATABASES_VAR} is not set. List the "
            f"database names that may be seeded."
        )

    url = make_url(db_url)

    host = (url.host or "").lower()
    if host not in hosts:
        # The host itself is not echoed back, so a misconfigured run cannot print
        # part of a production connection string into a shared terminal or log.
        raise RuntimeError(
            f"Refusing to seed: the target host is not listed in {ALLOWED_HOSTS_VAR}"
        )

    database = (url.database or "").lower()
    if database not in databases:
        raise RuntimeError(
            f"Refusing to seed: the target database is not listed in "
            f"{ALLOWED_DATABASES_VAR}"
        )


def require_reset_confirmation(reset_requested: bool) -> None:
    """Truncation is opt-in: without --reset the script must not destroy data."""
    if not reset_requested:
        raise RuntimeError(
            "Refusing to truncate existing data. Re-run with --reset if you "
            "really want to erase every table in the target database."
        )


def require_demo_password(password: str | None) -> str:
    """The demo password comes from the environment; there is no default."""
    if not password:
        raise RuntimeError(
            f"{PASSWORD_VAR} must be set. The seed script no longer ships a "
            f"shared default password."
        )

    if len(password) < 8:
        raise RuntimeError(f"{PASSWORD_VAR} must be at least 8 characters")

    return password
