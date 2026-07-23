"""Rename ballots.vote_hash to ballots.ballot_commitment.

The column now stores an HMAC-SHA256 commitment over the ballot's canonical input
including its complete ciphertext, rather than a salted hash that proved only
that a row existed. The name is changed so the schema does not describe the value
inaccurately.

Data is preserved by the rename, but values written before this revision are the
old salted hashes and will NOT verify against the new scheme. That is intentional:
recomputing commitments here would attest to whatever the database currently
holds, which is not something this migration can vouch for. Reseed or re-cast to
obtain verifiable ballots.

Revision ID: 0003_ballot_commitment
Revises: 0002_ballot_config
"""

import sqlalchemy as sa
from alembic import op


revision = "0003_ballot_commitment"
down_revision = "0002_ballot_config"
branch_labels = None
depends_on = None


OLD_NAME = "vote_hash"
NEW_NAME = "ballot_commitment"


def _unique_constraint_name(bind, column_name: str) -> str | None:
    """Find the unique constraint covering exactly `column_name` on ballots."""
    inspector = sa.inspect(bind)

    for constraint in inspector.get_unique_constraints("ballots"):
        if constraint["column_names"] == [column_name]:
            return constraint["name"]

    return None


def _rename(bind, from_name: str, to_name: str) -> None:
    columns = {column["name"] for column in sa.inspect(bind).get_columns("ballots")}

    if to_name in columns:
        return  # already applied

    constraint_name = _unique_constraint_name(bind, from_name)

    op.alter_column("ballots", from_name, new_column_name=to_name)

    # Keep the constraint name consistent with the column it now covers. Renaming
    # a constraint is PostgreSQL-specific; on SQLite the batch rename above has
    # already rebuilt the table, so there is nothing further to do.
    if constraint_name and bind.dialect.name == "postgresql":
        op.execute(
            f'ALTER TABLE ballots RENAME CONSTRAINT "{constraint_name}" '
            f'TO "ballots_{to_name}_key"'
        )


def upgrade() -> None:
    _rename(op.get_bind(), OLD_NAME, NEW_NAME)


def downgrade() -> None:
    _rename(op.get_bind(), NEW_NAME, OLD_NAME)
