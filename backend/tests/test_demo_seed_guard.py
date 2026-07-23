"""Unit tests for the demo-seed fail-closed guard."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models.election import BallotType
import scripts.seed_demo as seed_demo
from scripts.demo_seed_guard import (
    require_demo_password,
    require_reset_confirmation,
    require_safe_demo_database,
)


SAFE_URL = "postgresql://user:pw@localhost:5432/evoting_demo"


def _check(db_url=SAFE_URL, seed_allowed="true", hosts="localhost", databases="evoting_demo"):
    require_safe_demo_database(
        db_url,
        seed_allowed=seed_allowed,
        allowed_hosts=hosts,
        allowed_databases=databases,
    )


def test_allows_a_fully_allowlisted_target():
    _check()  # must not raise


def test_allowlists_are_case_insensitive_and_accept_multiple_entries():
    _check(hosts="Localhost, db.internal", databases="other_db, EVOTING_DEMO")


def test_rejects_missing_database_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _check(db_url=None)


@pytest.mark.parametrize("value", [None, "", "false", "1", "yes", "TRUE_ISH"])
def test_rejects_without_explicit_opt_in(value):
    """Only the exact string 'true' arms the script."""
    with pytest.raises(RuntimeError, match="DEMO_SEED_ALLOWED=true"):
        _check(seed_allowed=value)


def test_accepts_opt_in_case_insensitively():
    _check(seed_allowed="TRUE")


def test_rejects_when_host_allowlist_is_unset():
    """An unset allowlist must refuse, never wave the run through."""
    with pytest.raises(RuntimeError, match="DEMO_SEED_ALLOWED_HOSTS"):
        _check(hosts=None)


def test_rejects_when_database_allowlist_is_unset():
    with pytest.raises(RuntimeError, match="DEMO_SEED_ALLOWED_DATABASES"):
        _check(databases=None)


def test_rejects_host_outside_the_allowlist():
    with pytest.raises(RuntimeError, match="host"):
        _check(db_url="postgresql://user:pw@db.example.supabase.co:5432/evoting_demo")


def test_rejects_database_outside_the_allowlist():
    with pytest.raises(RuntimeError, match="database"):
        _check(db_url="postgresql://user:pw@localhost:5432/production")


def test_rejection_message_does_not_echo_the_target_host():
    """A misconfigured run must not print part of a connection string."""
    with pytest.raises(RuntimeError) as error:
        _check(db_url="postgresql://user:pw@secret-host.example.com:5432/evoting_demo")

    assert "secret-host" not in str(error.value)


def test_reset_is_required_before_truncating():
    with pytest.raises(RuntimeError, match="--reset"):
        require_reset_confirmation(False)


def test_reset_confirmation_passes_when_requested():
    require_reset_confirmation(True)  # must not raise


def test_password_must_be_provided():
    with pytest.raises(RuntimeError, match="DEMO_SEED_PASSWORD"):
        require_demo_password(None)


def test_password_must_not_be_empty():
    with pytest.raises(RuntimeError, match="DEMO_SEED_PASSWORD"):
        require_demo_password("")


def test_password_must_meet_minimum_length():
    with pytest.raises(RuntimeError, match="8 characters"):
        require_demo_password("short")


def test_password_is_returned_when_valid():
    assert require_demo_password("longenough123") == "longenough123"


def test_schema_behind_alembic_head_is_rejected():
    """Having an alembic_version row is not enough; it must equal current head."""
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        connection.execute(
            sa.text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('0001_baseline')"
            )
        )

    try:
        with Session(engine) as db:
            with pytest.raises(RuntimeError, match="Alembic head"):
                seed_demo.require_schema_at_head(db)
    finally:
        engine.dispose()


class RecordingSession:
    """Records statements instead of running them, and never commits."""

    def __init__(self):
        self.commit_calls = 0
        self.statements = []

    def execute(self, statement, parameters=None):
        self.statement = statement
        self.statements.append((str(statement), parameters))

    def commit(self):
        self.commit_calls += 1


def test_reset_tables_does_not_commit_its_own_transaction():
    """The caller must be able to roll the truncation back if seeding fails."""
    db = RecordingSession()

    seed_demo.reset_tables(db)

    assert db.commit_calls == 0


def test_reset_tables_restarts_the_audit_chain():
    """Clearing audit_logs without resetting the head would leave a broken chain.

    The next event would claim sequence N+1 with nothing before it, which
    verify_audit_chain reports as tampering on a database that was only reseeded.
    """
    db = RecordingSession()

    seed_demo.reset_tables(db)

    truncate = next(sql for sql, _ in db.statements if "TRUNCATE" in sql)
    assert "audit_logs" in truncate
    assert "audit_chain_head" in truncate

    reseed = [
        (sql, params)
        for sql, params in db.statements
        if "INSERT INTO audit_chain_head" in sql
    ]
    assert len(reseed) == 1, "the chain head must be seeded back to genesis"

    _, params = reseed[0]
    assert params["id"] == seed_demo.CHAIN_ID
    assert params["head_hash"] == seed_demo.GENESIS_HASH


def test_seed_commits_once_only_after_tally_and_verification(monkeypatch):
    """No partial seed state may be committed before the final verification."""

    class RecordingSession:
        def __init__(self):
            self.commit_calls = 0
            self.rollback_calls = 0

        def add(self, value):
            pass

        def flush(self):
            pass

        def refresh(self, value):
            pass

        def commit(self):
            self.commit_calls += 1

        def rollback(self):
            self.rollback_calls += 1

        def close(self):
            pass

    db = RecordingSession()
    observed = {}

    monkeypatch.setattr(seed_demo, "SessionLocal", lambda: db)
    monkeypatch.setattr(seed_demo, "require_safe_demo_database", lambda *args, **kwargs: None)
    monkeypatch.setattr(seed_demo, "require_reset_confirmation", lambda *args, **kwargs: None)
    monkeypatch.setattr(seed_demo, "require_demo_password", lambda value: "safe-password")
    monkeypatch.setattr(seed_demo, "require_schema_at_head", lambda session: None)
    monkeypatch.setattr(seed_demo, "reset_tables", lambda session: None)
    monkeypatch.setattr(
        seed_demo,
        "create_user",
        lambda *args, **kwargs: SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(seed_demo, "create_and_store_keypair", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        seed_demo,
        "create_candidates",
        lambda *args, **kwargs: [
            SimpleNamespace(id=uuid4(), name=name)
            for name in args[2]
        ],
    )
    monkeypatch.setattr(
        seed_demo,
        "add_eligible_voters",
        lambda *args, **kwargs: [SimpleNamespace(id=uuid4()) for _ in args[2]],
    )
    monkeypatch.setattr(seed_demo, "add_encrypted_ballot", lambda *args, **kwargs: None)

    def fake_tally(*args, **kwargs):
        observed["commits_before_tally"] = db.commit_calls
        observed["commit_requested"] = kwargs.get("commit")

    monkeypatch.setattr(seed_demo, "_tally_and_complete", fake_tally)
    monkeypatch.setattr(
        seed_demo,
        "verify_completed_tally",
        lambda *args, **kwargs: seed_demo.EXPECTED_COMPLETED_TALLY,
    )

    seed_demo.main(["--reset"])

    assert observed["commits_before_tally"] == 0
    assert observed["commit_requested"] is False
    assert db.commit_calls == 1


def test_seeded_ballot_timestamp_is_inside_election_window(monkeypatch):
    """Historical demo ballots must still be valid ballots, not late votes."""

    class RecordingSession:
        def add(self, value):
            self.added = value

        def flush(self):
            pass

    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 5)
    election = SimpleNamespace(
        id=uuid4(),
        public_key_n="demo-key",
        start_date=start,
        end_date=end,
        # Read by the shared ballot-commitment input.
        ballot_type=BallotType.single,
        max_selections=1,
    )
    voter_record = SimpleNamespace(id=uuid4(), voted_at=None)
    candidates = [SimpleNamespace(id=uuid4()) for _ in range(3)]

    monkeypatch.setattr(seed_demo, "deserialize_public_key", lambda value: object())
    monkeypatch.setattr(seed_demo, "encrypt_vote", lambda *args, **kwargs: '{"ciphertext": "x"}')
    monkeypatch.setattr(seed_demo, "now_sgt", lambda: datetime(2026, 1, 10))

    ballot = seed_demo.add_encrypted_ballot(
        RecordingSession(),
        election,
        voter_record,
        candidates,
        candidates[0],
    )

    assert start <= ballot.submitted_at <= end
    assert voter_record.voted_at == ballot.submitted_at
