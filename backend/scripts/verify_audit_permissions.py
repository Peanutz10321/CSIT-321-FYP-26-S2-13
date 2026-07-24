"""
Verify the *effective* database privileges on the audit tables.

The hash chain makes audit tampering detectable; database permissions are what
make it hard. This script checks that the role the application connects as can
append to the audit trail but cannot rewrite or erase it.

It is READ-ONLY. It runs only ``SELECT has_table_privilege(...)`` and never issues
GRANT, REVOKE, or any DDL/DML. It is safe to run against production.

Why ``has_table_privilege`` rather than ``information_schema.role_table_grants``:
the latter lists only privileges granted *directly* to the role. It misses
privileges inherited from other roles and privileges granted to ``PUBLIC``. A
role can therefore pass an ``information_schema`` check yet still be able to
DELETE through an inherited or PUBLIC grant. ``has_table_privilege`` answers the
question that actually matters — can this role, effectively, do X — so it is the
authority here.

A common misconfiguration this catches: pointing the application at the database
*owner* (or any superuser). An owner implicitly holds every privilege regardless
of GRANT/REVOKE, so ``has_table_privilege`` returns true across the board and this
script reports the deny checks as failures. Revoking privileges from an owner does
nothing; the fix is a dedicated non-owner application role. See MIGRATIONS.md.

Usage
-----
    python -m scripts.verify_audit_permissions                 # DATABASE_URL
    python -m scripts.verify_audit_permissions --db-url URL    # explicit target

Exit code is 0 when every requirement holds and 1 otherwise, so it can gate a
deployment.
"""

from __future__ import annotations

import argparse
import sys

import sqlalchemy as sa

from app.config import settings


# Tables are named schema-qualified throughout, so the check can never resolve a
# same-named table in another schema via a surprising search_path.
AUDIT_SCHEMA = "public"

# For each table: the privilege -> whether the application role must hold it.
# True  = must be allowed (append/read path).
# False = must be denied  (tamper path: the role must not be able to do this).
REQUIRED_PRIVILEGES: dict[str, dict[str, bool]] = {
    "public.audit_logs": {
        "INSERT": True,
        "SELECT": True,
        "UPDATE": False,
        "DELETE": False,
        "TRUNCATE": False,
    },
    "public.audit_chain_head": {
        # The head row is rewritten on every append, so UPDATE is required.
        "SELECT": True,
        "INSERT": True,
        "UPDATE": True,
        "DELETE": False,
        "TRUNCATE": False,
    },
}


class AuditPermissionProblem:
    def __init__(self, table: str, privilege: str, expected: bool, actual: bool):
        self.table = table
        self.privilege = privilege
        self.expected = expected
        self.actual = actual

    def __str__(self) -> str:
        if self.expected:
            return (
                f"{self.table}: {self.privilege} is DENIED but the application "
                f"role needs it to append/read the audit trail"
            )
        return (
            f"{self.table}: {self.privilege} is ALLOWED but the application role "
            f"must not be able to {self.privilege.lower()} audit rows"
        )


def _effective_privilege(connection, table: str, privilege: str) -> bool:
    """Whether the current role effectively holds `privilege` on `table`."""
    return bool(
        connection.execute(
            sa.text("SELECT has_table_privilege(:table, :privilege)"),
            {"table": table, "privilege": privilege},
        ).scalar()
    )


def check_effective_privileges(connection) -> list[AuditPermissionProblem]:
    """Compare the current role's effective privileges against the requirements.

    Pure and read-only; reusable by tests. Returns an empty list when the role is
    configured correctly.
    """
    problems: list[AuditPermissionProblem] = []

    for table, privileges in REQUIRED_PRIVILEGES.items():
        for privilege, expected in privileges.items():
            actual = _effective_privilege(connection, table, privilege)
            if actual != expected:
                problems.append(
                    AuditPermissionProblem(table, privilege, expected, actual)
                )

    return problems


def _reject_non_postgres(db_url: str) -> None:
    backend = sa.engine.make_url(db_url).get_backend_name()
    if backend != "postgresql":
        raise SystemExit(
            f"Refusing to run: audit-permission verification is PostgreSQL-only "
            f"(has_table_privilege). The configured database is '{backend}'. "
            f"SQLite has no per-table role privileges to check."
        )


def _require_audit_tables(connection) -> None:
    """Fail clearly if the audit tables are absent, rather than mid-check."""
    missing = [
        table
        for table in REQUIRED_PRIVILEGES
        if not connection.execute(
            sa.text("SELECT to_regclass(:qualified)"),
            {"qualified": table},
        ).scalar()
    ]
    if missing:
        raise SystemExit(
            f"Audit tables not found: {', '.join(missing)}. Run 'alembic upgrade "
            f"head' first (this database is not migrated)."
        )


def _describe_role(connection) -> tuple[str, bool]:
    """Return (current role, owns_any_audit_table)."""
    role = connection.execute(sa.text("SELECT current_user")).scalar()
    owns = connection.execute(
        sa.text(
            "SELECT bool_or(tableowner = current_user) FROM pg_tables "
            "WHERE schemaname = :schema "
            "AND tablename IN ('audit_logs', 'audit_chain_head')"
        ),
        {"schema": AUDIT_SCHEMA},
    ).scalar()
    return role, bool(owns)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=None, help="Target database URL.")
    args = parser.parse_args()

    db_url = args.db_url or settings.DATABASE_URL
    _reject_non_postgres(db_url)

    engine = sa.create_engine(db_url)
    try:
        with engine.connect() as connection:
            _require_audit_tables(connection)
            role, owns = _describe_role(connection)
            print(f"Checking effective audit-table privileges for role '{role}'.")
            if owns:
                print(
                    "WARNING: this role OWNS an audit table. An owner implicitly "
                    "holds every privilege, so REVOKE has no effect. Use a "
                    "dedicated non-owner application role (see MIGRATIONS.md)."
                )

            problems = check_effective_privileges(connection)
    finally:
        engine.dispose()

    if problems:
        print(f"\nFAIL - {len(problems)} problem(s):\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nOK - the application role can append to but not rewrite the audit trail.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
