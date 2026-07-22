"""Add ballot configuration columns to elections.

``elections.ballot_type`` and ``elections.max_selections`` were added to the
SQLAlchemy model by the multi-select ballot work. This revision adds them.

Both columns are NOT NULL with a server_default, so existing rows are backfilled
in place (every pre-existing election becomes a single-choice ballot with one
selection, which is what those elections actually were).

The column additions are guarded by an inspector check so this revision is safe
to run against a database where the columns were already added by hand.

Revision ID: 0002_ballot_config
Revises: 0001_baseline
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0002_ballot_config"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


BALLOT_TYPE = sa.Enum("single", "multi", name="ballot_type")


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("elections")}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns()

    if bind.dialect.name == "postgresql":
        # Create the named type up front (checkfirst keeps it idempotent), then
        # reference it with create_type=False so ADD COLUMN does not try to
        # CREATE TYPE a second time and fail.
        BALLOT_TYPE.create(bind, checkfirst=True)
        ballot_type = postgresql.ENUM(
            "single", "multi", name="ballot_type", create_type=False
        )
    else:
        # SQLite has no named enum type; this renders as VARCHAR + CHECK.
        ballot_type = sa.Enum("single", "multi", name="ballot_type")

    if "ballot_type" not in existing:
        op.add_column(
            "elections",
            sa.Column(
                "ballot_type",
                ballot_type,
                nullable=False,
                server_default="single",
            ),
        )

    if "max_selections" not in existing:
        op.add_column(
            "elections",
            sa.Column(
                "max_selections",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )


def downgrade() -> None:
    existing = _existing_columns()

    if "max_selections" in existing:
        op.drop_column("elections", "max_selections")

    if "ballot_type" in existing:
        op.drop_column("elections", "ballot_type")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        BALLOT_TYPE.drop(bind, checkfirst=True)
