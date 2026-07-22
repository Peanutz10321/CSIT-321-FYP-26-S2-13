"""Baseline schema.

The split matters for the two supported paths:

* Fresh database  -> ``alembic upgrade head`` runs 0001 then 0002.
* Existing database -> ``alembic stamp 0001`` then ``alembic upgrade head``,
  which applies only 0002. Stamping is correct here because the tables in 0001
  already exist; running it would fail on the existing objects.

See MIGRATIONS.md for the exact procedure.

Revision ID: 0001_baseline
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.Enum("voter", "organizer", "system_admin", name="user_role"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "suspended", name="user_status"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "elections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organizer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "completed",
                "cancelled",
                "archived",
                name="election_status",
            ),
            nullable=False,
        ),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("public_key_n", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organizer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # The Fernet-wrapped Paillier private key lives in its own table so that read
    # access to `elections` never yields decryption capability.
    op.create_table(
        "election_keys",
        sa.Column("election_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["election_id"], ["elections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("election_id"),
    )

    op.create_table(
        "candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("election_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo_url", sa.String(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["election_id"], ["elections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("election_id", "name", name="uq_candidates_election_name"),
    )

    # One row per (election, voter). The unique constraint is what stops the same
    # voter being enrolled in one election twice.
    op.create_table(
        "election_voters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("election_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "eligibility_status",
            sa.Enum("eligible", "revoked", name="eligibility_status"),
            nullable=False,
        ),
        sa.Column("voted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["election_id"], ["elections.id"]),
        sa.ForeignKeyConstraint(["voter_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "election_id", "voter_id", name="uq_election_voters_election_voter"
        ),
    )

    # `election_voter_id` is UNIQUE: at most one ballot per enrolled voter.
    op.create_table(
        "ballots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("election_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("election_voter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encrypted_vote", sa.Text(), nullable=False),
        sa.Column("vote_hash", sa.String(), nullable=False),
        sa.Column("receipt_code", sa.String(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "bulletin_status",
            sa.Enum("published", "hidden_invalid", name="bulletin_status"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["election_id"], ["elections.id"]),
        sa.ForeignKeyConstraint(["election_voter_id"], ["election_voters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("election_voter_id"),
        sa.UniqueConstraint("vote_hash"),
        sa.UniqueConstraint("receipt_code"),
    )

    op.create_table(
        "candidate_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("election_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_votes", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"]),
        sa.ForeignKeyConstraint(["election_id"], ["elections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "election_id", "candidate_id", name="uq_candidate_results_election_candidate"
        ),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("candidate_results")
    op.drop_table("ballots")
    op.drop_table("election_voters")
    op.drop_table("candidates")
    op.drop_table("election_keys")
    op.drop_table("elections")
    op.drop_table("users")

    # PostgreSQL keeps enum types after the tables using them are dropped.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum_name in (
            "bulletin_status",
            "eligibility_status",
            "election_status",
            "user_status",
            "user_role",
        ):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
