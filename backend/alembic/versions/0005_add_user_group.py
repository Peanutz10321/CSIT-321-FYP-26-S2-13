"""Add the optional organisation column to users.

``users.group`` was added to the SQLAlchemy model by the grouping work, which lets
a voter record an organisation at registration and lets an organizer enrol every
member of one at once. This revision adds the column and its lookup index.

The column is nullable with no server_default, so existing rows are left exactly as
they are and simply read back as NULL — nobody is retroactively placed in a group.
That also keeps the migration a metadata-only change on PostgreSQL rather than a
table rewrite.

The index is non-unique and matches the name SQLAlchemy derives from
``index=True`` (``ix_users_group``). It has to match, or ``compare_metadata`` in
tests/test_migrations_postgres.py reports the migrated schema as drifting from the
models. Many users share one organisation, so uniqueness would be wrong.

Column and index creation are guarded by inspector checks, the same way revision
0002 is, so this is safe to run against a database where either was already added
by hand.

Revision ID: 0005_user_group
Revises: 0004_audit_chain
"""

import sqlalchemy as sa
from alembic import op


revision = "0005_user_group"
down_revision = "0004_audit_chain"
branch_labels = None
depends_on = None


GROUP_COLUMN = "group"
GROUP_INDEX = "ix_users_group"

# Frozen at the width this revision actually created, deliberately NOT imported
# from app.models.user. A migration records what it did to the database at a point
# in time; importing the model would let a later edit to GROUP_MAX_LENGTH silently
# rewrite this revision's history, so a database migrated last month would no
# longer match what the file claims. Widening the column later is a new revision.
# The same reasoning is spelled out in 0004 for its hashing contract.
GROUP_MAX_LENGTH = 50


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("users")}


def _existing_indexes() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes("users")}


def upgrade() -> None:
    if GROUP_COLUMN not in _existing_columns():
        op.add_column(
            "users",
            # "group" is a reserved word in SQL; Alembic quotes the identifier for
            # us because the name is passed as data rather than interpolated.
            sa.Column(GROUP_COLUMN, sa.String(length=GROUP_MAX_LENGTH), nullable=True),
        )

    if GROUP_INDEX not in _existing_indexes():
        op.create_index(GROUP_INDEX, "users", [GROUP_COLUMN], unique=False)


def downgrade() -> None:
    # Index first: dropping the column would take the index with it on PostgreSQL,
    # but doing it explicitly and in this order keeps the revision correct on any
    # backend and leaves no orphaned object behind.
    if GROUP_INDEX in _existing_indexes():
        op.drop_index(GROUP_INDEX, table_name="users")

    if GROUP_COLUMN in _existing_columns():
        op.drop_column("users", GROUP_COLUMN)
