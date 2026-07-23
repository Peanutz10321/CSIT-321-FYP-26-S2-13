"""
End-to-end tests for the demo seed against a real PostgreSQL database.

PostgreSQL is required because the seed uses TRUNCATE ... RESTART IDENTITY
CASCADE, which SQLite does not support, and because the point of these tests is
that the demo data is produced by the production close/tally path.

These are slow: seeding generates two 2048-bit Paillier keypairs and runs a real
homomorphic tally. They are skipped unless TEST_POSTGRES_URL is set (see
tests/test_migrations_postgres.py for the throwaway-database command).
"""

import importlib
import json
import os

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from scripts.destructive_test_guard import require_safe_postgres_test_database


TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL is not set; see this module's docstring",
)

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXPECTED_TALLY = {"Daniel Wong": 2, "Emily Chen": 1, "Farhan Aziz": 1}
DEMO_PASSWORD = "seed-test-password"


@pytest.fixture
def load_seed(monkeypatch):
    """Reload the seed module bound to the throwaway PostgreSQL database.

    app.database creates its engine at import time, so it has to be reloaded for
    the seed to target PostgreSQL. The original URL is restored on teardown:
    without that, conftest's per-test cleanup would keep running against this
    database after the test finishes.
    """
    import app.config
    import app.database
    import scripts.seed_demo

    original_url = app.config.settings.DATABASE_URL

    def _load():
        monkeypatch.setenv("DEMO_SEED_ALLOWED", "true")
        monkeypatch.setenv("DEMO_SEED_ALLOWED_HOSTS", "localhost,127.0.0.1")
        monkeypatch.setenv("DEMO_SEED_ALLOWED_DATABASES", "evoting_test")
        monkeypatch.setenv("DEMO_SEED_PASSWORD", DEMO_PASSWORD)

        app.config.settings.DATABASE_URL = TEST_POSTGRES_URL
        importlib.reload(app.database)
        return importlib.reload(scripts.seed_demo)

    yield _load

    app.config.settings.DATABASE_URL = original_url
    importlib.reload(app.database)
    importlib.reload(scripts.seed_demo)


def _rebuild_schema(revision: str | None = "head"):
    """Drop public and optionally migrate the replacement schema to a revision."""
    require_safe_postgres_test_database(
        TEST_POSTGRES_URL,
        destructive_tests_allowed=os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS"),
    )

    engine = sa.create_engine(TEST_POSTGRES_URL)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    engine.dispose()

    if revision:
        config = Config(os.path.join(BACKEND_ROOT, "alembic.ini"))
        config.set_main_option("script_location", os.path.join(BACKEND_ROOT, "alembic"))
        config.set_main_option("sqlalchemy.url", TEST_POSTGRES_URL)
        command.upgrade(config, revision)


@pytest.fixture
def seeded_engine(load_seed):
    """A migrated PostgreSQL database with the demo seed applied."""
    _rebuild_schema()
    load_seed().main(["--reset"])

    engine = sa.create_engine(TEST_POSTGRES_URL)
    try:
        yield engine
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# The seeded demo data is real tally output
# ---------------------------------------------------------------------------


def test_completed_election_has_stored_results(seeded_engine):
    """The bug this replaces: a completed-looking election with no results."""
    with seeded_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT c.name, r.total_votes "
                "FROM candidate_results r "
                "JOIN candidates c ON c.id = r.candidate_id"
            )
        ).all()

    assert {name: total for name, total in rows} == EXPECTED_TALLY


def test_completed_election_is_marked_completed(seeded_engine):
    with seeded_engine.connect() as connection:
        status = connection.execute(
            sa.text(
                "SELECT status FROM elections "
                "WHERE title = 'Completed Organization Voting Event 2026'"
            )
        ).scalar_one()

    assert status == "completed"


def test_results_are_published(seeded_engine):
    with seeded_engine.connect() as connection:
        unpublished = connection.execute(
            sa.text("SELECT count(*) FROM candidate_results WHERE published_at IS NULL")
        ).scalar_one()

    assert unpublished == 0


def test_close_and_publication_are_audited(seeded_engine):
    """Proof the production close path ran, rather than a seed-only shortcut."""
    with seeded_engine.connect() as connection:
        actions = connection.execute(
            sa.text("SELECT action FROM audit_logs")
        ).scalars().all()

    assert "election_closed" in actions
    assert "results_published" in actions


def test_totals_equal_the_number_of_ballots_cast(seeded_engine):
    with seeded_engine.connect() as connection:
        ballots = connection.execute(
            sa.text(
                "SELECT count(*) FROM ballots b "
                "JOIN elections e ON e.id = b.election_id "
                "WHERE e.title = 'Completed Organization Voting Event 2026'"
            )
        ).scalar_one()
        total_votes = connection.execute(
            sa.text("SELECT coalesce(sum(total_votes), 0) FROM candidate_results")
        ).scalar_one()

    assert total_votes == ballots == 4


def test_seeded_ballots_hold_real_ciphertext(seeded_engine):
    """Seeded ballots must be genuinely encrypted, not plaintext 0/1 markers.

    Candidate IDs are legitimately present as JSON keys — the vector covers every
    candidate. The property that matters is that the per-candidate *values* are
    Paillier ciphertexts, so the stored row does not reveal the selection.
    """
    with seeded_engine.connect() as connection:
        encrypted_votes = connection.execute(
            sa.text("SELECT encrypted_vote FROM ballots")
        ).scalars().all()

    assert encrypted_votes

    for encrypted_vote in encrypted_votes:
        for entry in json.loads(encrypted_vote).values():
            ciphertext = entry["c"]
            assert ciphertext not in ("0", "1")
            assert len(ciphertext) > 100, "ciphertext is too short to be Paillier output"


def test_seeded_ballots_are_inside_the_election_window(seeded_engine):
    with seeded_engine.connect() as connection:
        invalid_ballots = connection.execute(
            sa.text(
                "SELECT count(*) "
                "FROM ballots b "
                "JOIN elections e ON e.id = b.election_id "
                "WHERE b.submitted_at < e.start_date "
                "OR b.submitted_at > e.end_date"
            )
        ).scalar_one()

    assert invalid_ballots == 0


def test_active_demo_election_is_left_open(seeded_engine):
    with seeded_engine.connect() as connection:
        status = connection.execute(
            sa.text(
                "SELECT status FROM elections "
                "WHERE title = 'Community Leadership Voting Event 2026'"
            )
        ).scalar_one()

    assert status == "active"


def test_seed_does_not_stamp_or_bypass_alembic(seeded_engine):
    """The seed must not create tables itself; Alembic stays the schema owner."""
    with seeded_engine.connect() as connection:
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert revision == "0002_ballot_config"


# ---------------------------------------------------------------------------
# Guards refuse before touching data
# ---------------------------------------------------------------------------


def test_seed_refuses_without_reset_flag(load_seed):
    seed = load_seed()

    with pytest.raises(RuntimeError, match="--reset"):
        seed.main([])


def test_seed_refuses_when_not_armed(load_seed, monkeypatch):
    seed = load_seed()
    monkeypatch.delenv("DEMO_SEED_ALLOWED")

    with pytest.raises(RuntimeError, match="DEMO_SEED_ALLOWED=true"):
        seed.main(["--reset"])


def test_seed_refuses_when_database_not_allowlisted(load_seed, monkeypatch):
    seed = load_seed()
    monkeypatch.setenv("DEMO_SEED_ALLOWED_DATABASES", "some_other_database")

    with pytest.raises(RuntimeError, match="database"):
        seed.main(["--reset"])


def test_seed_refuses_without_a_password(load_seed, monkeypatch):
    seed = load_seed()
    monkeypatch.delenv("DEMO_SEED_PASSWORD")

    with pytest.raises(RuntimeError, match="DEMO_SEED_PASSWORD"):
        seed.main(["--reset"])


def test_seed_refuses_on_a_database_without_alembic(load_seed):
    """A database built by something other than Alembic must be rejected."""
    _rebuild_schema(revision=None)

    seed = load_seed()

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        seed.main(["--reset"])


def test_seed_refuses_behind_head_without_deleting_existing_data(load_seed):
    """A stamped but outdated database must be rejected before TRUNCATE."""
    _rebuild_schema(revision="0001_baseline")

    engine = sa.create_engine(TEST_POSTGRES_URL)
    sentinel_id = "00000000-0000-0000-0000-000000000001"
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users "
                "(id, role, status, external_id, username, full_name, email, password_hash) "
                "VALUES "
                "(:id, 'voter', 'active', 'SENTINEL-001', 'sentinel', "
                "'Sentinel User', 'sentinel@example.test', 'not-a-real-hash')"
            ),
            {"id": sentinel_id},
        )

    seed = load_seed()

    with pytest.raises(RuntimeError, match="Alembic head"):
        seed.main(["--reset"])

    with engine.connect() as connection:
        remaining = connection.execute(
            sa.text("SELECT count(*) FROM users WHERE id = :id"),
            {"id": sentinel_id},
        ).scalar_one()
    engine.dispose()

    assert remaining == 1


def test_seed_rolls_back_reset_when_population_fails(load_seed, monkeypatch):
    """A failure after TRUNCATE must restore the database's previous contents."""
    _rebuild_schema()

    engine = sa.create_engine(TEST_POSTGRES_URL)
    sentinel_id = "00000000-0000-0000-0000-000000000002"
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users "
                "(id, role, status, external_id, username, full_name, email, password_hash) "
                "VALUES "
                "(:id, 'voter', 'active', 'SENTINEL-002', 'rollback_sentinel', "
                "'Rollback Sentinel', 'rollback-sentinel@example.test', "
                "'not-a-real-hash')"
            ),
            {"id": sentinel_id},
        )

    seed = load_seed()
    monkeypatch.setattr(
        seed,
        "create_user",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced failure")),
    )

    with pytest.raises(RuntimeError, match="forced failure"):
        seed.main(["--reset"])

    with engine.connect() as connection:
        remaining = connection.execute(
            sa.text("SELECT count(*) FROM users WHERE id = :id"),
            {"id": sentinel_id},
        ).scalar_one()
    engine.dispose()

    assert remaining == 1
