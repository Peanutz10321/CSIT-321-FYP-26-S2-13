"""
Vote/close race tests. PostgreSQL only.

SQLite cannot exercise any of this: it has no row-level locking, and SQLAlchemy
omits FOR SHARE / FOR UPDATE entirely on that dialect. These tests therefore run
against a real PostgreSQL database with real concurrent sessions.

The interleavings are made deterministic rather than raced: one session holds the
close's exclusive lock open while another thread attempts to vote, and the test
asserts the voter actually blocks. A timing-based race would pass by luck.

Setup command is in tests/test_migrations_postgres.py; these tests additionally
need ALLOW_DESTRUCTIVE_DB_TESTS=true.
"""

import os
import threading
import time
import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.core.time import now_sgt
from app.models.ballot import Ballot
from app.models.candidate import Candidate
from app.models.candidate_result import CandidateResult
from app.models.election import Election, ElectionStatus
from app.models.election_key import ElectionKey
from app.models.election_voter import ElectionVoter, EligibilityStatus
from app.models.user import User, UserRole, UserStatus
import app.routes.election_routes as election_routes_module
import app.routes.vote_routes as vote_routes_module
from app.routes.election_routes import _finalize_election_close, _tally_and_complete
from app.routes.vote_routes import submitVote
from app.schemas.vote_schema import VoteCreate
from app.security.homomorphic import (
    generate_keypair,
    serialize_private_key,
    serialize_public_key,
)
from app.security.password import hash_password
from app.services.election_lock import lock_election_for_close
from scripts.destructive_test_guard import require_safe_postgres_test_database


TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL is not set; see this module's docstring",
)

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Upper bound for any wait in this module. Blocking is never asserted by elapsed
# time — it is confirmed via pg_stat_activity — so this is only a failure timeout,
# not a probe window, and can be generous without weakening any assertion.
COMPLETION_TIMEOUT_SECONDS = 30


@pytest.fixture(scope="module")
def keypair():
    """One Paillier keypair for the whole module.

    Key generation dominates the runtime of these tests, and the race being tested
    is independent of which key is used, so the same pair is reused across
    elections instead of calling create_and_store_keypair per test.
    """
    return generate_keypair()


@pytest.fixture(scope="module")
def pg_sessionmaker():
    """A migrated PostgreSQL database and a sessionmaker bound to it."""
    require_safe_postgres_test_database(
        TEST_POSTGRES_URL,
        destructive_tests_allowed=os.getenv("ALLOW_DESTRUCTIVE_DB_TESTS"),
    )

    engine = sa.create_engine(TEST_POSTGRES_URL)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))

    config = Config(os.path.join(BACKEND_ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_ROOT, "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_POSTGRES_URL)
    command.upgrade(config, "head")

    try:
        yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    finally:
        engine.dispose()


@pytest.fixture
def scenario(pg_sessionmaker, keypair):
    """A fresh active election with three candidates and four eligible voters."""
    public_key, private_key = keypair
    suffix = uuid.uuid4().hex[:8]

    db = pg_sessionmaker()
    try:
        organizer = User(
            role=UserRole.organizer,
            status=UserStatus.active,
            external_id=f"ORG-{suffix}",
            username=f"organizer_{suffix}",
            email=f"organizer_{suffix}@test.com",
            password_hash=hash_password("testing123"),
        )
        db.add(organizer)

        voters = []
        for index in range(4):
            voter = User(
                role=UserRole.voter,
                status=UserStatus.active,
                external_id=f"VOTER-{suffix}-{index}",
                username=f"voter_{suffix}_{index}",
                email=f"voter_{suffix}_{index}@test.com",
                password_hash=hash_password("testing123"),
            )
            db.add(voter)
            voters.append(voter)

        db.flush()

        now = now_sgt()
        election = Election(
            organizer_id=organizer.id,
            title=f"Race Election {suffix}",
            status=ElectionStatus.active,
            start_date=now - timedelta(hours=1),
            end_date=now + timedelta(days=1),
            public_key_n=serialize_public_key(public_key),
        )
        db.add(election)
        db.flush()

        # Store the shared private key directly rather than generating a new one.
        encrypted = (
            Fernet(settings.KEYSTORE_MASTER_SECRET.encode())
            .encrypt(serialize_private_key(private_key).encode())
            .decode()
        )
        db.add(ElectionKey(election_id=election.id, encrypted_private_key=encrypted))

        candidates = []
        for order, name in enumerate(["Ada", "Grace", "Alan"], start=1):
            candidate = Candidate(
                election_id=election.id,
                name=f"{name} {suffix}",
                display_order=order,
            )
            db.add(candidate)
            candidates.append(candidate)

        election_voters = []
        for voter in voters:
            record = ElectionVoter(
                election_id=election.id,
                voter_id=voter.id,
                eligibility_status=EligibilityStatus.eligible,
            )
            db.add(record)
            election_voters.append(record)

        db.commit()

        return {
            "sessionmaker": pg_sessionmaker,
            "election_id": election.id,
            "organizer_id": organizer.id,
            "organizer": organizer,
            "voter_ids": [voter.id for voter in voters],
            "candidate_ids": [candidate.id for candidate in candidates],
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vote(scenario, voter_index, candidate_index=0):
    """Run the real submitVote route in its own session. Returns (result, error)."""
    db = scenario["sessionmaker"]()
    try:
        voter = db.get(User, scenario["voter_ids"][voter_index])
        payload = VoteCreate(
            election_id=scenario["election_id"],
            candidate_id=scenario["candidate_ids"][candidate_index],
        )
        try:
            return submitVote(payload, db=db, current_voter=voter), None
        except HTTPException as error:
            return None, error
    finally:
        db.close()


def _close(scenario):
    """Run the real close workflow in its own session. Returns (result, error)."""
    db = scenario["sessionmaker"]()
    try:
        organizer = db.get(User, scenario["organizer_id"])
        try:
            return _finalize_election_close(db, scenario["election_id"], organizer), None
        except HTTPException as error:
            db.rollback()
            return None, error
    finally:
        db.close()


def _counts(scenario):
    """Ballot count, summed candidate totals, and election status."""
    db = scenario["sessionmaker"]()
    try:
        ballots = (
            db.query(Ballot)
            .filter(Ballot.election_id == scenario["election_id"])
            .count()
        )
        tallied = (
            db.query(sa.func.coalesce(sa.func.sum(CandidateResult.total_votes), 0))
            .filter(CandidateResult.election_id == scenario["election_id"])
            .scalar()
        )
        status = db.get(Election, scenario["election_id"]).status
        return ballots, int(tallied), status
    finally:
        db.close()


def _postgres_backend_pid(db):
    """Return the PostgreSQL process id for a worker session."""
    return int(db.execute(sa.text("SELECT pg_backend_pid()")).scalar())


def _wait_until_postgres_reports_lock_wait(sessionmaker, backend_pid):
    """Wait until PostgreSQL confirms that a worker is blocked on a lock.

    Thread-start and timeout checks alone cannot prove an operation reached the
    database lock: an unscheduled worker would look blocked too. pg_stat_activity
    exposes the server-side wait state, so this helper makes the interleaving an
    observed PostgreSQL fact rather than a scheduling assumption.
    """
    deadline = time.monotonic() + COMPLETION_TIMEOUT_SECONDS
    monitor = sessionmaker()
    try:
        while time.monotonic() < deadline:
            wait_event_type = monitor.execute(
                sa.text(
                    "SELECT wait_event_type "
                    "FROM pg_stat_activity "
                    "WHERE pid = :backend_pid"
                ),
                {"backend_pid": backend_pid},
            ).scalar()
            monitor.rollback()

            if wait_event_type == "Lock":
                return

            time.sleep(0.02)
    finally:
        monitor.close()

    pytest.fail(
        f"PostgreSQL session {backend_pid} never entered a server-side lock wait"
    )


# ---------------------------------------------------------------------------
# A vote racing an in-progress close
# ---------------------------------------------------------------------------


def test_vote_blocks_while_a_close_holds_the_lock_then_is_rejected(
    scenario, monkeypatch
):
    """The central race.

    A close holds the election row exclusively. A voter that arrives mid-close
    must not slip a ballot in: it blocks on the lock, and once the close commits
    it re-reads the completed status and is rejected.
    """
    closing_db: Session = scenario["sessionmaker"]()
    outcome = {}
    vote_finished = threading.Event()
    vote_lock_attempted = threading.Event()
    vote_backend_pid = {}
    voter_thread = None
    real_vote_lock = vote_routes_module.lock_election_for_vote

    def observed_vote_lock(db, election_id):
        vote_backend_pid["value"] = _postgres_backend_pid(db)
        vote_lock_attempted.set()
        return real_vote_lock(db, election_id)

    monkeypatch.setattr(
        vote_routes_module, "lock_election_for_vote", observed_vote_lock
    )

    def cast_vote():
        try:
            outcome["result"], outcome["error"] = _vote(scenario, voter_index=0)
        finally:
            vote_finished.set()

    try:
        # Close transaction: take the exclusive lock and hold it open.
        election = lock_election_for_close(closing_db, scenario["election_id"])
        assert election.status == ElectionStatus.active

        voter_thread = threading.Thread(target=cast_vote, daemon=True)
        voter_thread.start()

        assert vote_lock_attempted.wait(timeout=COMPLETION_TIMEOUT_SECONDS), (
            "the vote never attempted to acquire its shared election lock"
        )
        _wait_until_postgres_reports_lock_wait(
            scenario["sessionmaker"], vote_backend_pid["value"]
        )
        assert not vote_finished.is_set()

        # Complete the close, releasing the lock.
        _tally_and_complete(closing_db, election, scenario["organizer_id"])
    finally:
        closing_db.close()
        if voter_thread is not None:
            voter_thread.join(timeout=COMPLETION_TIMEOUT_SECONDS)

    assert vote_finished.wait(timeout=COMPLETION_TIMEOUT_SECONDS), (
        "the vote never unblocked after the close committed"
    )

    assert outcome["result"] is None, "a ballot was accepted after the tally ran"
    assert outcome["error"] is not None
    assert outcome["error"].status_code == 400
    assert "active" in outcome["error"].detail.lower()

    ballots, tallied, status = _counts(scenario)
    assert status == ElectionStatus.completed
    assert ballots == 0
    assert tallied == 0


def test_no_receipt_exists_for_a_ballot_missing_from_the_tally(scenario, monkeypatch):
    """A successful receipt must always correspond to a counted ballot."""
    voter_count = 3

    closing_db: Session = scenario["sessionmaker"]()
    outcomes = []
    outcomes_lock = threading.Lock()
    done = threading.Event()
    finished = {"count": 0}
    worker_errors = []

    vote_backend_pids = []
    pids_lock = threading.Lock()
    all_votes_attempted = threading.Event()
    real_vote_lock = vote_routes_module.lock_election_for_vote

    def observed_vote_lock(db, election_id):
        with pids_lock:
            vote_backend_pids.append(_postgres_backend_pid(db))
            if len(vote_backend_pids) == voter_count:
                all_votes_attempted.set()
        return real_vote_lock(db, election_id)

    monkeypatch.setattr(
        vote_routes_module, "lock_election_for_vote", observed_vote_lock
    )

    def cast_vote(index):
        try:
            result, error = _vote(scenario, voter_index=index)
            with outcomes_lock:
                outcomes.append((result, error))
        except Exception as error:
            worker_errors.append(error)
        finally:
            with outcomes_lock:
                finished["count"] += 1
                if finished["count"] == voter_count:
                    done.set()

    threads = [
        threading.Thread(target=cast_vote, args=(index,), daemon=True)
        for index in range(voter_count)
    ]

    try:
        election = lock_election_for_close(closing_db, scenario["election_id"])

        for thread in threads:
            thread.start()

        assert all_votes_attempted.wait(timeout=COMPLETION_TIMEOUT_SECONDS), (
            "not every voter reached its shared election lock"
        )
        # Each voter must be waiting on the row lock server-side rather than
        # merely being unscheduled, so the close below is genuinely contended.
        for backend_pid in vote_backend_pids:
            _wait_until_postgres_reports_lock_wait(
                scenario["sessionmaker"], backend_pid
            )
        assert not done.is_set()

        _tally_and_complete(closing_db, election, scenario["organizer_id"])
    finally:
        closing_db.close()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=COMPLETION_TIMEOUT_SECONDS)

    assert done.wait(timeout=COMPLETION_TIMEOUT_SECONDS)
    assert not worker_errors

    receipts = [result for result, _ in outcomes if result is not None]
    ballots, tallied, status = _counts(scenario)

    assert status == ElectionStatus.completed
    # Every issued receipt must be backed by a ballot that the tally counted.
    assert len(receipts) == ballots == tallied


def test_in_progress_vote_blocks_close_then_is_counted(scenario, monkeypatch):
    """A vote holding the shared lock commits before the waiting close tallies."""
    vote_lock_acquired = threading.Event()
    release_vote = threading.Event()
    close_lock_attempted = threading.Event()
    vote_finished = threading.Event()
    close_finished = threading.Event()
    close_backend_pid = {}
    vote_outcome = {}
    close_outcome = {}
    worker_errors = []

    real_vote_lock = vote_routes_module.lock_election_for_vote
    real_close_lock = election_routes_module.lock_election_for_close

    def paused_vote_lock(db, election_id):
        election = real_vote_lock(db, election_id)
        vote_lock_acquired.set()
        if not release_vote.wait(timeout=COMPLETION_TIMEOUT_SECONDS):
            raise AssertionError("the test never released the in-progress vote")
        return election

    def observed_close_lock(db, election_id):
        close_backend_pid["value"] = _postgres_backend_pid(db)
        close_lock_attempted.set()
        return real_close_lock(db, election_id)

    monkeypatch.setattr(
        vote_routes_module, "lock_election_for_vote", paused_vote_lock
    )
    monkeypatch.setattr(
        election_routes_module, "lock_election_for_close", observed_close_lock
    )

    def cast_vote():
        try:
            vote_outcome["result"], vote_outcome["error"] = _vote(
                scenario, voter_index=0, candidate_index=0
            )
        except Exception as error:
            worker_errors.append(error)
        finally:
            vote_finished.set()

    def close_election():
        try:
            close_outcome["result"], close_outcome["error"] = _close(scenario)
        except Exception as error:
            worker_errors.append(error)
        finally:
            close_finished.set()

    voter_thread = threading.Thread(target=cast_vote, daemon=True)
    close_thread = threading.Thread(target=close_election, daemon=True)

    try:
        voter_thread.start()
        assert vote_lock_acquired.wait(timeout=COMPLETION_TIMEOUT_SECONDS), (
            "the vote never acquired its shared election lock"
        )

        close_thread.start()
        assert close_lock_attempted.wait(timeout=COMPLETION_TIMEOUT_SECONDS), (
            "the close never attempted to acquire its exclusive election lock"
        )
        _wait_until_postgres_reports_lock_wait(
            scenario["sessionmaker"], close_backend_pid["value"]
        )
        assert not close_finished.is_set()
    finally:
        release_vote.set()
        if voter_thread.ident is not None:
            voter_thread.join(timeout=COMPLETION_TIMEOUT_SECONDS)
        if close_thread.ident is not None:
            close_thread.join(timeout=COMPLETION_TIMEOUT_SECONDS)

    assert vote_finished.is_set()
    assert close_finished.is_set()
    assert not voter_thread.is_alive()
    assert not close_thread.is_alive()

    assert not worker_errors
    assert vote_outcome["error"] is None, vote_outcome["error"]
    assert vote_outcome["result"].receipt_code
    assert close_outcome["error"] is None, close_outcome["error"]

    ballots, tallied, status = _counts(scenario)
    assert status == ElectionStatus.completed
    assert ballots == 1
    assert tallied == 1


def test_turnout_equals_the_tallied_ballot_count(scenario):
    """Turnout is a live COUNT(*); it must not exceed what was tallied.

    Single-select with no abstentions, so the candidate totals sum to exactly one
    per ballot. A ballot landing after the tally would break this equality.
    """
    for index in range(3):
        _, error = _vote(scenario, voter_index=index, candidate_index=index % 3)
        assert error is None, error

    _, close_error = _close(scenario)
    assert close_error is None, close_error

    # A late voter must now be refused outright.
    late_result, late_error = _vote(scenario, voter_index=3)
    assert late_result is None
    assert late_error.status_code == 400

    ballots, tallied, status = _counts(scenario)
    assert status == ElectionStatus.completed
    assert ballots == tallied == 3


def test_candidate_totals_match_the_final_ballot_set(scenario):
    """Per-candidate totals, not just the sum, must reflect the ballots cast."""
    # Two for the first candidate, one for the second.
    for voter_index, candidate_index in [(0, 0), (1, 0), (2, 1)]:
        _, error = _vote(scenario, voter_index=voter_index, candidate_index=candidate_index)
        assert error is None, error

    _, close_error = _close(scenario)
    assert close_error is None, close_error

    db = scenario["sessionmaker"]()
    try:
        totals = {
            row.candidate_id: row.total_votes
            for row in db.query(CandidateResult)
            .filter(CandidateResult.election_id == scenario["election_id"])
            .all()
        }
    finally:
        db.close()

    candidate_ids = scenario["candidate_ids"]
    assert totals[candidate_ids[0]] == 2
    assert totals[candidate_ids[1]] == 1
    assert totals[candidate_ids[2]] == 0


# ---------------------------------------------------------------------------
# Concurrent closes
# ---------------------------------------------------------------------------


def test_two_concurrent_closes_tally_exactly_once(scenario, monkeypatch):
    """A double tally would double the stored totals."""
    for index in range(2):
        _, error = _vote(scenario, voter_index=index, candidate_index=0)
        assert error is None, error

    results = []
    results_lock = threading.Lock()
    call_count_lock = threading.Lock()
    first_lock_acquired = threading.Event()
    release_first_close = threading.Event()
    second_lock_attempted = threading.Event()
    second_lock_acquired = threading.Event()
    second_backend_pid = {}
    worker_errors = []
    lock_call_count = 0
    real_close_lock = election_routes_module.lock_election_for_close

    def coordinated_close_lock(db, election_id):
        nonlocal lock_call_count
        with call_count_lock:
            lock_call_count += 1
            call_number = lock_call_count

        if call_number == 1:
            election = real_close_lock(db, election_id)
            first_lock_acquired.set()
            if not release_first_close.wait(timeout=COMPLETION_TIMEOUT_SECONDS):
                raise AssertionError("the test never released the first close")
            return election

        second_backend_pid["value"] = _postgres_backend_pid(db)
        second_lock_attempted.set()
        election = real_close_lock(db, election_id)
        second_lock_acquired.set()
        return election

    monkeypatch.setattr(
        election_routes_module, "lock_election_for_close", coordinated_close_lock
    )

    def close():
        try:
            outcome = _close(scenario)
            with results_lock:
                results.append(outcome)
        except Exception as error:
            worker_errors.append(error)

    first_thread = threading.Thread(target=close, daemon=True)
    second_thread = threading.Thread(target=close, daemon=True)
    threads = [first_thread, second_thread]

    try:
        first_thread.start()
        assert first_lock_acquired.wait(timeout=COMPLETION_TIMEOUT_SECONDS), (
            "the first close never acquired its exclusive election lock"
        )

        second_thread.start()
        assert second_lock_attempted.wait(timeout=COMPLETION_TIMEOUT_SECONDS), (
            "the second close never attempted to acquire the election lock"
        )
        _wait_until_postgres_reports_lock_wait(
            scenario["sessionmaker"], second_backend_pid["value"]
        )
        assert not second_lock_acquired.is_set()
    finally:
        release_first_close.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=COMPLETION_TIMEOUT_SECONDS)

    for thread in threads:
        assert not thread.is_alive(), "a close never completed"

    assert not worker_errors
    assert len(results) == 2
    assert second_lock_acquired.is_set()

    closed_ok = [result for result, error in results if error is None]
    rejected = [error for _, error in results if error is not None]

    assert len(closed_ok) == 1, "more than one close succeeded"
    assert len(rejected) == 1
    assert rejected[0].status_code == 400

    ballots, tallied, status = _counts(scenario)
    assert status == ElectionStatus.completed
    assert ballots == 2
    assert tallied == 2, "the tally ran twice and doubled the totals"


def test_a_second_close_after_completion_is_rejected(scenario):
    """Sequential double close: the status guard under the lock stops it."""
    _, error = _vote(scenario, voter_index=0)
    assert error is None, error

    _, first_error = _close(scenario)
    assert first_error is None

    _, second_error = _close(scenario)
    assert second_error is not None
    assert second_error.status_code == 400

    ballots, tallied, _ = _counts(scenario)
    assert ballots == tallied == 1
