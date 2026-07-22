"""
Migration and constraint tests that require a real PostgreSQL database.

SQLite cannot validate any of this: it has no named enum types, it rewrites
tables rather than altering them, and its constraint behaviour differs from
PostgreSQL's. These tests therefore run only when TEST_POSTGRES_URL is set.

Start a throwaway database with:

    docker run --rm -d -p 55432:5432 \
        -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=evoting_test \
        --name evoting-test-pg postgres:16

    export TEST_POSTGRES_URL=postgresql://postgres:postgres@localhost:55432/evoting_test

NEVER point TEST_POSTGRES_URL at the deployed database: the fixture below drops
and recreates the public schema before every test.
"""

import os
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.database import Base
import app.models  # noqa: F401  (registers all tables on Base.metadata)


TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL is not set; see this module's docstring",
)

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _alembic_config() -> Config:
    config = Config(os.path.join(BACKEND_ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_ROOT, "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_POSTGRES_URL)
    return config


@pytest.fixture
def pg_engine():
    """A completely empty PostgreSQL database, rebuilt for every test."""
    engine = sa.create_engine(TEST_POSTGRES_URL)

    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def upgraded_engine(pg_engine):
    """An empty database with all migrations applied."""
    command.upgrade(_alembic_config(), "head")
    return pg_engine


def _columns(engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


# ---------------------------------------------------------------------------
# Fresh-database path
# ---------------------------------------------------------------------------


def test_fresh_database_upgrade_creates_every_model_table(upgraded_engine):
    actual = set(sa.inspect(upgraded_engine).get_table_names())

    for table_name in Base.metadata.tables:
        assert table_name in actual, f"{table_name} was not created by the migrations"


def test_fresh_database_schema_matches_models_exactly(upgraded_engine):
    """The migrations and the models must not drift apart.

    This is the regression test for the bug that motivated this work: a model
    change that never reached the database. Alembic's autogenerate diff is
    empty only when the migrated schema matches Base.metadata.
    """
    with upgraded_engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={"compare_type": True},
        )
        diff = compare_metadata(context, Base.metadata)

    assert diff == [], f"migrated schema differs from the models: {diff}"


def test_ballot_type_is_a_real_enum_type(upgraded_engine):
    """ballot_type must be a native PostgreSQL enum, not a bare varchar."""
    with upgraded_engine.connect() as connection:
        labels = connection.execute(
            sa.text(
                "SELECT e.enumlabel FROM pg_type t "
                "JOIN pg_enum e ON t.oid = e.enumtypid "
                "WHERE t.typname = 'ballot_type' "
                "ORDER BY e.enumsortorder"
            )
        ).scalars().all()

    assert labels == ["single", "multi"]


# ---------------------------------------------------------------------------
# Existing-database upgrade path
# ---------------------------------------------------------------------------


def test_legacy_database_gains_ballot_config_columns(pg_engine):
    """Simulates the deployed database: baseline schema, then upgrade.

    Revision 0001 represents what create_all() had already built. Upgrading to
    head must add the two columns that create_all() could never have added, and
    must backfill existing rows rather than failing on the NOT NULL.
    """
    config = _alembic_config()

    command.upgrade(config, "0001_baseline")

    assert "ballot_type" not in _columns(pg_engine, "elections")
    assert "max_selections" not in _columns(pg_engine, "elections")

    # An election that predates the ballot-configuration work.
    organizer_id = uuid.uuid4()
    election_id = uuid.uuid4()
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, role, status, external_id, username, "
                "email, password_hash) VALUES (:id, 'organizer', 'active', "
                "'ORG-001', 'legacy_org', 'legacy@test.com', 'x')"
            ),
            {"id": organizer_id},
        )
        connection.execute(
            sa.text(
                "INSERT INTO elections (id, organizer_id, title, status, "
                "start_date) VALUES (:id, :organizer_id, 'Legacy Election', "
                "'completed', now())"
            ),
            {"id": election_id, "organizer_id": organizer_id},
        )

    command.upgrade(config, "head")

    assert "ballot_type" in _columns(pg_engine, "elections")
    assert "max_selections" in _columns(pg_engine, "elections")

    # The pre-existing row must be backfilled to a valid single-choice ballot.
    with pg_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT ballot_type, max_selections FROM elections WHERE id = :id"
            ),
            {"id": election_id},
        ).one()

    assert row.ballot_type == "single"
    assert row.max_selections == 1


def test_ballot_config_upgrade_is_idempotent(pg_engine):
    """Safe to run even where the columns were already added by hand."""
    config = _alembic_config()
    command.upgrade(config, "0001_baseline")

    # Someone patched the live database manually before the migration existed.
    with pg_engine.begin() as connection:
        connection.execute(sa.text("CREATE TYPE ballot_type AS ENUM ('single', 'multi')"))
        connection.execute(
            sa.text(
                "ALTER TABLE elections ADD COLUMN ballot_type ballot_type "
                "NOT NULL DEFAULT 'single'"
            )
        )
        connection.execute(
            sa.text(
                "ALTER TABLE elections ADD COLUMN max_selections INTEGER "
                "NOT NULL DEFAULT 1"
            )
        )

    command.upgrade(config, "head")  # must not raise

    assert "ballot_type" in _columns(pg_engine, "elections")
    assert "max_selections" in _columns(pg_engine, "elections")


def test_downgrade_returns_to_baseline(upgraded_engine):
    command.downgrade(_alembic_config(), "0001_baseline")

    assert "ballot_type" not in _columns(upgraded_engine, "elections")
    assert "max_selections" not in _columns(upgraded_engine, "elections")


# ---------------------------------------------------------------------------
# Constraint enforcement — the guarantees the security model depends on
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded(upgraded_engine):
    """A voter enrolled in one election, with one ballot already cast."""
    ids = {
        "organizer": uuid.uuid4(),
        "voter": uuid.uuid4(),
        "election": uuid.uuid4(),
        "election_voter": uuid.uuid4(),
        "ballot": uuid.uuid4(),
    }

    with upgraded_engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, role, status, external_id, username, "
                "email, password_hash) VALUES "
                "(:organizer, 'organizer', 'active', 'ORG-001', 'org1', "
                "'org1@test.com', 'x'), "
                "(:voter, 'voter', 'active', 'VOTER-001', 'voter1', "
                "'voter1@test.com', 'x')"
            ),
            ids,
        )
        connection.execute(
            sa.text(
                "INSERT INTO elections (id, organizer_id, title, status, "
                "start_date, ballot_type, max_selections) VALUES "
                "(:election, :organizer, 'E', 'active', now(), 'single', 1)"
            ),
            ids,
        )
        connection.execute(
            sa.text(
                "INSERT INTO election_voters (id, election_id, voter_id, "
                "eligibility_status) VALUES "
                "(:election_voter, :election, :voter, 'eligible')"
            ),
            ids,
        )
        connection.execute(
            sa.text(
                "INSERT INTO ballots (id, election_id, election_voter_id, "
                "encrypted_vote, vote_hash, receipt_code, bulletin_status) "
                "VALUES (:ballot, :election, :election_voter, 'ct', 'hash-1', "
                "'RCPT-1', 'published')"
            ),
            ids,
        )

    return upgraded_engine, ids


def test_second_ballot_for_same_election_voter_is_rejected(seeded):
    """One ballot per enrolled voter, enforced by the database itself.

    Note this enforces uniqueness only. It is not a fix for the vote/close race
    condition, which is tracked separately in the remediation plan.
    """
    engine, ids = seeded

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO ballots (id, election_id, election_voter_id, "
                    "encrypted_vote, vote_hash, receipt_code, bulletin_status) "
                    "VALUES (:new_id, :election, :election_voter, 'ct2', "
                    "'hash-2', 'RCPT-2', 'published')"
                ),
                {**ids, "new_id": uuid.uuid4()},
            )


def test_duplicate_receipt_code_is_rejected(seeded):
    engine, ids = seeded

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            other_voter = uuid.uuid4()
            other_election_voter = uuid.uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, role, status, external_id, username, "
                    "email, password_hash) VALUES (:id, 'voter', 'active', "
                    "'VOTER-002', 'voter2', 'voter2@test.com', 'x')"
                ),
                {"id": other_voter},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO election_voters (id, election_id, voter_id, "
                    "eligibility_status) VALUES (:id, :election, :voter, 'eligible')"
                ),
                {"id": other_election_voter, "election": ids["election"], "voter": other_voter},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO ballots (id, election_id, election_voter_id, "
                    "encrypted_vote, vote_hash, receipt_code, bulletin_status) "
                    "VALUES (:id, :election, :election_voter, 'ct2', 'hash-2', "
                    "'RCPT-1', 'published')"  # duplicate receipt code
                ),
                {
                    "id": uuid.uuid4(),
                    "election": ids["election"],
                    "election_voter": other_election_voter,
                },
            )


def test_duplicate_vote_hash_is_rejected(seeded):
    engine, ids = seeded

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            other_voter = uuid.uuid4()
            other_election_voter = uuid.uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, role, status, external_id, username, "
                    "email, password_hash) VALUES (:id, 'voter', 'active', "
                    "'VOTER-003', 'voter3', 'voter3@test.com', 'x')"
                ),
                {"id": other_voter},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO election_voters (id, election_id, voter_id, "
                    "eligibility_status) VALUES (:id, :election, :voter, 'eligible')"
                ),
                {"id": other_election_voter, "election": ids["election"], "voter": other_voter},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO ballots (id, election_id, election_voter_id, "
                    "encrypted_vote, vote_hash, receipt_code, bulletin_status) "
                    "VALUES (:id, :election, :election_voter, 'ct2', 'hash-1', "
                    "'RCPT-2', 'published')"  # duplicate vote hash
                ),
                {
                    "id": uuid.uuid4(),
                    "election": ids["election"],
                    "election_voter": other_election_voter,
                },
            )


def test_duplicate_election_voter_enrollment_is_rejected(seeded):
    engine, ids = seeded

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO election_voters (id, election_id, voter_id, "
                    "eligibility_status) VALUES (:id, :election, :voter, 'eligible')"
                ),
                {"id": uuid.uuid4(), "election": ids["election"], "voter": ids["voter"]},
            )


# ---------------------------------------------------------------------------
# The verification script
# ---------------------------------------------------------------------------


def test_verify_schema_passes_on_migrated_database(upgraded_engine):
    from scripts.verify_schema import verify

    assert verify(TEST_POSTGRES_URL) == []


def test_verify_schema_detects_a_missing_column(pg_engine):
    """The script must actually catch drift, not just always pass."""
    from scripts.verify_schema import verify

    command.upgrade(_alembic_config(), "head")

    with pg_engine.begin() as connection:
        connection.execute(sa.text("ALTER TABLE elections DROP COLUMN max_selections"))

    problems = verify(TEST_POSTGRES_URL)

    assert any("max_selections" in problem for problem in problems), problems


def test_verify_schema_detects_missing_uniqueness(pg_engine):
    from scripts.verify_schema import verify

    command.upgrade(_alembic_config(), "head")

    with pg_engine.begin() as connection:
        connection.execute(
            sa.text("ALTER TABLE ballots DROP CONSTRAINT ballots_receipt_code_key")
        )

    problems = verify(TEST_POSTGRES_URL)

    assert any("receipt_code" in problem for problem in problems), problems
