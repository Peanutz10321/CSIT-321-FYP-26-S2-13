"""Hash-chain the audit log.

Adds ``sequence_number``, ``previous_hash`` and ``entry_hash`` to audit_logs,
plus the singleton ``audit_chain_head`` row that writers lock to append safely.

Existing audit rows predate the chain, so they are backfilled here: they are
ordered by (created_at, id), numbered from 1, and linked together exactly the
way the application links new entries. Without that, the first verification
after deployment would report every historical row as broken.

The hashing helper is imported from app.security.audit rather than copied. A
copy would be frozen at today's format while verification kept using the
application's, and the two would silently disagree about every backfilled row.

Revision ID: 0003_audit_chain
Revises: 0002_ballot_config
"""

import sqlalchemy as sa
from alembic import op

from app.core.time import now_sgt
from app.security.audit import CHAIN_ID, GENESIS_HASH, compute_entry_hash


revision = "0003_audit_chain"
down_revision = "0002_ballot_config"
branch_labels = None
depends_on = None


CHAIN_COLUMNS = ("sequence_number", "previous_hash", "entry_hash")


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _backfill_chain(bind) -> tuple[int, str]:
    """Link every pre-existing audit row. Returns the resulting chain tip."""
    rows = bind.execute(
        sa.text(
            "SELECT id, actor_user_id, action, entity_type, entity_id, "
            "details, created_at FROM audit_logs ORDER BY created_at, id"
        )
    ).mappings().all()

    sequence_number = 0
    previous_hash = GENESIS_HASH

    for row in rows:
        sequence_number += 1
        entry_hash = compute_entry_hash(
            sequence_number=sequence_number,
            previous_hash=previous_hash,
            actor_user_id=row["actor_user_id"],
            action=row["action"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            details=row["details"],
            created_at=row["created_at"],
        )

        bind.execute(
            sa.text(
                "UPDATE audit_logs SET sequence_number = :sequence_number, "
                "previous_hash = :previous_hash, entry_hash = :entry_hash "
                "WHERE id = :id"
            ),
            {
                "sequence_number": sequence_number,
                "previous_hash": previous_hash,
                "entry_hash": entry_hash,
                "id": row["id"],
            },
        )

        previous_hash = entry_hash

    return sequence_number, previous_hash


def upgrade() -> None:
    bind = op.get_bind()

    if "audit_chain_head" not in _existing_tables():
        op.create_table(
            "audit_chain_head",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("sequence_number", sa.BigInteger(), nullable=False),
            sa.Column("head_hash", sa.String(length=64), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    existing = _existing_columns("audit_logs")

    # Added nullable so the backfill below has somewhere to write; tightened to
    # NOT NULL once every row is linked.
    for column in CHAIN_COLUMNS:
        if column in existing:
            continue
        op.add_column(
            "audit_logs",
            sa.Column(
                column,
                sa.BigInteger() if column == "sequence_number" else sa.String(length=64),
                nullable=True,
            ),
        )

    sequence_number, head_hash = _backfill_chain(bind)

    already_seeded = bind.execute(
        sa.text("SELECT 1 FROM audit_chain_head WHERE id = :id"),
        {"id": CHAIN_ID},
    ).first()

    if already_seeded is None:
        bind.execute(
            sa.text(
                "INSERT INTO audit_chain_head "
                "(id, sequence_number, head_hash, updated_at) "
                "VALUES (:id, :sequence_number, :head_hash, :updated_at)"
            ),
            {
                "id": CHAIN_ID,
                "sequence_number": sequence_number,
                "head_hash": head_hash,
                "updated_at": now_sgt(),
            },
        )

    with op.batch_alter_table("audit_logs") as batch:
        batch.alter_column(
            "sequence_number", existing_type=sa.BigInteger(), nullable=False
        )
        batch.alter_column(
            "previous_hash", existing_type=sa.String(length=64), nullable=False
        )
        batch.alter_column(
            "entry_hash", existing_type=sa.String(length=64), nullable=False
        )
        batch.create_unique_constraint(
            "uq_audit_logs_sequence_number", ["sequence_number"]
        )


def downgrade() -> None:
    existing = _existing_columns("audit_logs")

    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_constraint("uq_audit_logs_sequence_number", type_="unique")

    for column in CHAIN_COLUMNS:
        if column in existing:
            op.drop_column("audit_logs", column)

    if "audit_chain_head" in _existing_tables():
        op.drop_table("audit_chain_head")
