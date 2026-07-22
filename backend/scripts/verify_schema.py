"""
Verify that a live database matches the SQLAlchemy models.

Read-only: this script never creates, alters, or drops anything. It is safe to
point at production.

It checks three things:

1. Every table the models declare exists.
2. Every column the models declare exists, with matching nullability.
3. The uniqueness constraints the security model depends on are actually
   present, by column set rather than by constraint name (Supabase may have
   auto-generated names such as ``ballots_receipt_code_key``).

Usage
-----
    # Against whatever DATABASE_URL the backend is configured with (.env):
    python -m scripts.verify_schema

    # Against an explicit database:
    python -m scripts.verify_schema --db-url "$SOME_DATABASE_URL"

Exit code is 0 when the schema matches and 1 when it does not, so this can be
used as a deployment gate.
"""

from __future__ import annotations

import argparse
import sys

import sqlalchemy as sa

from app.config import settings
from app.database import Base

# Registers every table on Base.metadata.
import app.models  # noqa: F401


# The uniqueness guarantees the application relies on, expressed as
# table -> list of column-sets that must each be unique.
#
# Constraint NAMES are deliberately not asserted: create_all() let PostgreSQL
# auto-name several of these, so the column set is the portable check.
REQUIRED_UNIQUE = {
    # At most one ballot per enrolled voter.
    "ballots": [
        {"election_voter_id"},
        {"receipt_code"},
        {"vote_hash"},
    ],
    # A voter is enrolled in a given election at most once.
    "election_voters": [
        {"election_id", "voter_id"},
    ],
    "candidates": [
        {"election_id", "name"},
    ],
    "candidate_results": [
        {"election_id", "candidate_id"},
    ],
    "users": [
        {"email"},
        {"username"},
        {"external_id"},
    ],
}


def _unique_column_sets(inspector: sa.Inspector, table: str) -> list[set[str]]:
    """All column-sets enforced unique on `table`, from any source.

    Uniqueness can come from a UNIQUE constraint, a unique index, or the primary
    key. All three genuinely enforce it, so all three count.
    """
    found: list[set[str]] = []

    for constraint in inspector.get_unique_constraints(table):
        found.append(set(constraint["column_names"]))

    for index in inspector.get_indexes(table):
        if index.get("unique"):
            found.append({c for c in index["column_names"] if c is not None})

    primary_key = inspector.get_pk_constraint(table)
    if primary_key.get("constrained_columns"):
        found.append(set(primary_key["constrained_columns"]))

    return found


def verify(db_url: str) -> list[str]:
    """Return a list of problems. Empty list means the schema matches."""
    problems: list[str] = []

    engine = sa.create_engine(db_url)
    try:
        inspector = sa.inspect(engine)
        actual_tables = set(inspector.get_table_names())

        for table_name, table in sorted(Base.metadata.tables.items()):
            if table_name not in actual_tables:
                problems.append(f"missing table: {table_name}")
                continue

            actual_columns = {c["name"]: c for c in inspector.get_columns(table_name)}

            for column in table.columns:
                actual = actual_columns.get(column.name)
                if actual is None:
                    problems.append(f"missing column: {table_name}.{column.name}")
                    continue

                if actual["nullable"] and not column.nullable:
                    problems.append(
                        f"nullability mismatch: {table_name}.{column.name} "
                        f"is nullable in the database but NOT NULL in the model"
                    )

        for table_name, required_sets in sorted(REQUIRED_UNIQUE.items()):
            if table_name not in actual_tables:
                continue  # already reported above

            enforced = _unique_column_sets(inspector, table_name)
            for required in required_sets:
                if required not in enforced:
                    problems.append(
                        f"missing uniqueness on {table_name}"
                        f"({', '.join(sorted(required))})"
                    )
    finally:
        engine.dispose()

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL to inspect. Defaults to the configured DATABASE_URL.",
    )
    args = parser.parse_args()

    db_url = args.db_url or settings.DATABASE_URL

    # Never print the URL — it carries credentials.
    engine_url = sa.engine.make_url(db_url)
    print(f"Verifying schema on {engine_url.get_backend_name()} database "
          f"'{engine_url.database}'...")

    problems = verify(db_url)

    if problems:
        print(f"\nFAIL - {len(problems)} problem(s):\n")
        for problem in problems:
            print(f"  - {problem}")
        print("\nRun 'alembic upgrade head' to apply outstanding migrations.")
        return 1

    print("\nOK - database schema matches the models.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
