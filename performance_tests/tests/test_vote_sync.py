"""Tests for the synchronized vote scenario and its coordinator.

Concurrency is exercised with real ``threading`` threads. That is the same code
path Locust drives under gevent, because ``gevent.monkey.patch_all()`` replaces
``threading``'s primitives with greenlet-aware ones — the coordinator never
imports gevent, so it behaves identically here.

Every request goes through ``FakeLocustClient``: no transport, no socket, no
``requests`` import. Nothing in this module can reach staging.
"""

from __future__ import annotations

import json
import threading
from datetime import timedelta

import pytest

from performance_tests import common, load_plan as lp, setup_performance_data as setup
from performance_tests import verify_performance_data as verify
from performance_tests import vote_coordinator as vc
from performance_tests.common import ConfigError, SafetyError
from performance_tests.vote_coordinator import (
    CoordinatorError,
    DuplicateVoterError,
    VoteCoordinator,
)

from .conftest import BATCH, FAKE_TOKEN, base_env
from .test_locustfile import FakeLocustClient, FakeResponse


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def prepared(api, config, data_dir, silent):
    setup.run_setup(
        config,
        assume_yes=True,
        transport=api.transport(),
        data_dir=data_dir,
        write=silent,
    )
    return json.loads(
        common.manifest_path(BATCH, data_dir).read_text(encoding="utf-8")
    )


def vote_env(run="1", **overrides):
    env = base_env(
        **{
            lp.ENV_SCENARIO: "vote",
            lp.ENV_VOTE_LOAD_ALLOWED: "true",
            lp.ENV_VOTE_ELECTION_RUN: run,
        }
    )
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


def plan_for(data_dir, run="1", **overrides):
    return lp.build_plan(vote_env(run, **overrides), data_dir=data_dir)


def live_election(plan, **overrides):
    """The election body GET /elections/{id} would return for a healthy run."""
    election = plan.vote_election
    now = common.now_sgt()
    body = {
        "id": election["election_id"],
        "organizer_id": "00000000-0000-0000-0000-000000000001",
        "organizer_username": f"perf_organizer_{BATCH}",
        "title": election["title"],
        "status": "active",
        "ballot_type": "single",
        "max_selections": 1,
        "start_date": common.format_sgt(now - timedelta(minutes=5)),
        "end_date": common.format_sgt(now + timedelta(hours=24)),
        "candidates": [
            {"id": c["id"], "name": c["name"], "display_order": i}
            for i, c in enumerate(election["candidates"], start=1)
        ],
    }
    body.update(overrides)
    return body


def ready_client(plan, *, history=None, election_body=None, vote_status=201):
    """A client that answers every request one prepared voter makes."""
    client = FakeLocustClient()
    election_id = plan.vote_election["election_id"]

    client.default = None
    client.queue(f"POST {common.LOGIN_PATH}", FakeResponse(200, {"access_token": FAKE_TOKEN}))
    client.queue(
        f"GET /elections/{election_id}",
        FakeResponse(200, election_body if election_body is not None else live_election(plan)),
    )
    client.queue(f"GET {lp.PATH_VOTE_HISTORY}", FakeResponse(200, history or []))
    client.queue(
        f"POST {lp.PATH_VOTES}", FakeResponse(vote_status, {"receipt_code": "RCPT-1"})
    )
    return client


# ── Coordinator: barrier mechanics ────────────────────────────────────────────


def test_coordinator_rejects_invalid_construction():
    with pytest.raises(ConfigError):
        VoteCoordinator(0, timeout_seconds=10)
    with pytest.raises(ConfigError):
        VoteCoordinator(10, timeout_seconds=0)
    with pytest.raises(ConfigError):
        VoteCoordinator(10, timeout_seconds=-5)


def test_a_voter_may_claim_only_one_account():
    coordinator = VoteCoordinator(2, timeout_seconds=5)
    coordinator.claim("perf_voter_001")

    with pytest.raises(DuplicateVoterError, match="claimed twice"):
        coordinator.claim("perf_voter_001")


def test_ready_requires_a_prior_claim():
    coordinator = VoteCoordinator(2, timeout_seconds=5)

    with pytest.raises(CoordinatorError, match="without claiming"):
        coordinator.mark_ready("perf_voter_001")


def test_barrier_holds_until_every_voter_is_ready():
    coordinator = VoteCoordinator(10, timeout_seconds=5)

    for index in range(1, 10):
        coordinator.claim(f"v{index}")
        coordinator.mark_ready(f"v{index}")
        assert coordinator.released is False, f"released early at {index} ready"

    assert coordinator.ready_count == 9

    coordinator.claim("v10")
    coordinator.mark_ready("v10")

    assert coordinator.released is True
    assert coordinator.may_vote() is True


def test_ten_users_block_until_the_tenth_becomes_ready():
    """Nine greenlets wait; none proceeds until the tenth arrives."""
    coordinator = VoteCoordinator(10, timeout_seconds=10)
    released: list[str] = []
    lock = threading.Lock()

    def waiter(name: str):
        coordinator.claim(name)
        coordinator.mark_ready(name)
        if coordinator.wait_for_release():
            with lock:
                released.append(name)

    threads = [threading.Thread(target=waiter, args=(f"v{i}",)) for i in range(1, 10)]
    for thread in threads:
        thread.start()

    # Give the nine a chance to reach the barrier and block there.
    for thread in threads:
        thread.join(timeout=0.5)
    assert released == [], "voters were released before the cohort was complete"
    assert all(thread.is_alive() for thread in threads)

    # The tenth completes the cohort.
    tenth = threading.Thread(target=waiter, args=("v10",))
    tenth.start()

    for thread in threads + [tenth]:
        thread.join(timeout=5)

    assert sorted(released) == sorted(f"v{i}" for i in range(1, 11))


def test_abort_releases_waiters_without_allowing_a_vote():
    coordinator = VoteCoordinator(3, timeout_seconds=10)
    outcomes: list[bool] = []
    lock = threading.Lock()

    def waiter(name: str):
        coordinator.claim(name)
        coordinator.mark_ready(name)
        allowed = coordinator.wait_for_release()
        with lock:
            outcomes.append(allowed)

    threads = [threading.Thread(target=waiter, args=(f"v{i}",)) for i in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=0.3)

    coordinator.abort("login failed", "v3")

    for thread in threads:
        thread.join(timeout=5)

    assert outcomes == [False, False]
    assert coordinator.aborted is True
    assert coordinator.attempts == 0


def test_readiness_timeout_aborts_without_releasing_votes():
    coordinator = VoteCoordinator(5, timeout_seconds=0.2)
    coordinator.claim("v1")
    coordinator.mark_ready("v1")

    assert coordinator.wait_for_release() is False
    assert coordinator.aborted is True
    assert "readiness timeout" in (coordinator.summary().abort_reason or "")
    assert coordinator.attempts == 0


def test_once_aborted_no_later_user_may_vote():
    coordinator = VoteCoordinator(3, timeout_seconds=5)
    coordinator.abort("something failed")

    coordinator.claim("v1")
    assert coordinator.mark_ready("v1") is False
    assert coordinator.wait_for_release() is False
    assert coordinator.may_vote() is False

    with pytest.raises(CoordinatorError, match="after the run was aborted"):
        coordinator.record_attempt()


def test_marking_ready_twice_is_refused():
    coordinator = VoteCoordinator(3, timeout_seconds=5)
    coordinator.claim("v1")
    coordinator.mark_ready("v1")

    with pytest.raises(CoordinatorError, match="ready twice"):
        coordinator.mark_ready("v1")


def test_more_ready_voters_than_expected_aborts():
    """A cohort larger than commissioned is refused rather than allowed to vote."""
    coordinator = VoteCoordinator(2, timeout_seconds=5)
    for name in ("v1", "v2"):
        coordinator.claim(name)
        coordinator.mark_ready(name)

    coordinator.claim("v3")
    assert coordinator.mark_ready("v3") is False
    assert coordinator.aborted is True


def test_concurrent_claims_are_race_safe():
    coordinator = VoteCoordinator(50, timeout_seconds=5)
    duplicates: list[str] = []
    start = threading.Event()

    def worker(name: str):
        start.wait()
        try:
            coordinator.claim(name)
        except DuplicateVoterError:
            duplicates.append(name)

    # Twenty threads all racing on the same ten names.
    names = [f"v{i % 10}" for i in range(20)]
    threads = [threading.Thread(target=worker, args=(n,)) for n in names]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join()

    assert len(coordinator.claimed) == 10
    assert len(duplicates) == 10


def test_summary_counters_are_correct():
    coordinator = VoteCoordinator(3, timeout_seconds=5)
    for name in ("v1", "v2", "v3"):
        coordinator.claim(name)
        coordinator.mark_ready(name)

    coordinator.record_attempt()
    coordinator.record_accepted()
    coordinator.record_attempt()
    coordinator.record_rejected("duplicate vote")
    coordinator.record_attempt()
    coordinator.record_accepted()

    summary = coordinator.summary()

    assert (summary.expected, summary.prepared) == (3, 3)
    assert (summary.attempts, summary.accepted, summary.failed) == (3, 2, 1)
    assert summary.aborted is False

    rendered = summary.render()
    assert "Expected voters: 3" in rendered
    assert "Prepared voters: 3" in rendered
    assert "Vote attempts:   3" in rendered
    assert "Accepted votes:  2" in rendered
    assert "Failed votes:    1" in rendered
    assert "Aborted:         no" in rendered


def test_summary_contains_no_secrets():
    coordinator = VoteCoordinator(1, timeout_seconds=5)
    coordinator.claim("v1")
    coordinator.mark_ready("v1")
    coordinator.record_attempt()
    coordinator.record_accepted()

    rendered = coordinator.summary().render()

    assert FAKE_TOKEN not in rendered
    assert "Bearer" not in rendered
    assert "password" not in rendered.lower()
    assert "RCPT" not in rendered


# ── Run / user-count mapping ──────────────────────────────────────────────────


@pytest.mark.parametrize(("run", "users"), [(1, 10), (2, 25), (3, 50)])
def test_commissioned_run_user_pairs_are_accepted(run, users):
    assert lp.require_run_user_count(run, users) == users


@pytest.mark.parametrize(
    ("run", "users"),
    [(1, 50), (1, 25), (1, 9), (1, 11), (2, 10), (2, 50), (3, 10), (3, 25), (3, 49)],
)
def test_run_user_count_mismatch_is_refused(run, users):
    with pytest.raises(SafetyError, match="must be voted by exactly"):
        lp.require_run_user_count(run, users)


def test_run_one_with_fifty_users_is_refused():
    """The example from the brief."""
    with pytest.raises(SafetyError, match="exactly 10 users"):
        lp.require_run_user_count(1, 50)


def test_expected_voters_comes_from_the_selected_run(prepared, data_dir):
    assert plan_for(data_dir, "1").expected_voters == 10
    assert plan_for(data_dir, "2").expected_voters == 25
    assert plan_for(data_dir, "3").expected_voters == 50


# ── Readiness timeout configuration ───────────────────────────────────────────


def test_readiness_timeout_defaults_to_ten_minutes(prepared, data_dir):
    assert plan_for(data_dir).vote_ready_timeout == 600.0


@pytest.mark.parametrize("value", ["0", "-1", "-0.5", "abc", "none", "1e", ""])
def test_invalid_readiness_timeout_is_refused(prepared, data_dir, value):
    if value == "":
        # Empty means "unset", which is the default rather than an error.
        assert plan_for(data_dir, **{lp.ENV_VOTE_READY_TIMEOUT: value}).vote_ready_timeout == 600.0
        return

    with pytest.raises(ConfigError):
        plan_for(data_dir, **{lp.ENV_VOTE_READY_TIMEOUT: value})


def test_readiness_timeout_covers_fifty_voters_at_the_documented_spawn_rate():
    """50 voters at --spawn-rate 0.2 take 250s to spawn; the default must exceed it."""
    spawn_seconds = 50 / 0.2

    assert lp.DEFAULT_VOTE_READY_TIMEOUT > spawn_seconds * 2


def test_custom_readiness_timeout_is_used(prepared, data_dir):
    plan = plan_for(data_dir, **{lp.ENV_VOTE_READY_TIMEOUT: "900"})

    assert plan.vote_ready_timeout == 900.0


# ── Readiness checks against the live election ────────────────────────────────


def test_a_healthy_voter_passes_readiness(prepared, data_dir):
    plan = plan_for(data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN
    client = ready_client(plan)
    client.responses.pop(f"POST {common.LOGIN_PATH}")

    assert session.check_vote_readiness(client) is None
    assert client.names == [lp.NAME_ELECTION_DETAIL, lp.NAME_VOTE_HISTORY]
    for call in client.calls:
        assert call.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"


def test_expired_selected_election_is_refused_at_readiness(prepared, data_dir):
    """The currently expired elections must be rejected cleanly."""
    plan = plan_for(data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN

    expired = live_election(plan, end_date="2020-01-01T00:00:00")
    client = ready_client(plan, election_body=expired)
    client.responses.pop(f"POST {common.LOGIN_PATH}")

    problem = session.check_vote_readiness(client)

    assert problem is not None
    assert "expired" in problem


def test_expired_election_in_the_manifest_is_refused_before_spawning(prepared, data_dir):
    """The plan itself refuses, so nothing spawns at all."""
    manifest = prepared
    manifest["elections"][0]["end_date"] = "2020-01-01T00:00:00"
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))

    with pytest.raises(SafetyError, match="Refusing to vote in an expired election"):
        plan_for(data_dir, "1")


def test_not_yet_started_election_is_refused(prepared, data_dir):
    plan = plan_for(data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN

    future = common.format_sgt(common.now_sgt() + timedelta(hours=1))
    client = ready_client(plan, election_body=live_election(plan, start_date=future))
    client.responses.pop(f"POST {common.LOGIN_PATH}")

    problem = session.check_vote_readiness(client)

    assert problem is not None and "has not started" in problem


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"status": "completed"}, "not 'active'"),
        ({"status": "draft"}, "not 'active'"),
        ({"ballot_type": "multi"}, "ballot_type"),
        ({"max_selections": 2}, "max_selections"),
        ({"candidates": []}, "candidates do not match"),
    ],
)
def test_misconfigured_election_is_refused(prepared, data_dir, overrides, fragment):
    plan = plan_for(data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN
    client = ready_client(plan, election_body=live_election(plan, **overrides))
    client.responses.pop(f"POST {common.LOGIN_PATH}")

    problem = session.check_vote_readiness(client)

    assert problem is not None and fragment in problem


def test_ineligible_voter_is_refused(prepared, data_dir):
    """403 from GET /elections/{id} is how the backend reports ineligibility."""
    plan = plan_for(data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN
    client = FakeLocustClient()
    client.queue(
        f"GET /elections/{plan.vote_election['election_id']}",
        FakeResponse(403, {"detail": "Election not found or you are not eligible"}),
    )

    problem = session.check_vote_readiness(client)

    assert problem == "not eligible for the selected election"
    assert client.verdicts == ["failure"]


def test_already_voted_voter_is_refused(prepared, data_dir):
    plan = plan_for(data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN
    history = [
        {
            "id": "b1",
            "election_id": plan.vote_election["election_id"],
            "election_title": plan.vote_election["title"],
            "receipt_code": "RCPT-OLD",
            "submitted_at": "2026-08-10T10:00:00",
            "bulletin_status": "published",
        }
    ]
    client = ready_client(plan, history=history)
    client.responses.pop(f"POST {common.LOGIN_PATH}")

    problem = session.check_vote_readiness(client)

    assert problem == "voter has already voted in the selected election"


def test_a_ballot_in_another_election_does_not_block_readiness(prepared, data_dir):
    """Voting in run 1 must not stop the same voter from voting in run 2."""
    plan = plan_for(data_dir, "2")
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN
    history = [
        {
            "id": "b1",
            "election_id": prepared["elections"][0]["election_id"],  # run 1
            "election_title": prepared["elections"][0]["title"],
            "receipt_code": "RCPT-RUN1",
            "submitted_at": "2026-08-10T10:00:00",
            "bulletin_status": "published",
        }
    ]
    client = ready_client(plan, history=history)
    client.responses.pop(f"POST {common.LOGIN_PATH}")

    assert session.check_vote_readiness(client) is None


def test_readiness_never_calls_the_results_endpoint(prepared, data_dir):
    plan = plan_for(data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN
    client = ready_client(plan)
    client.responses.pop(f"POST {common.LOGIN_PATH}")

    session.check_vote_readiness(client)

    assert not any("/results" in call.path for call in client.calls)


def test_unreadable_vote_history_aborts_readiness(prepared, data_dir):
    plan = plan_for(data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    session._token = FAKE_TOKEN
    client = FakeLocustClient()
    client.queue(
        f"GET /elections/{plan.vote_election['election_id']}",
        FakeResponse(200, live_election(plan)),
    )
    client.queue(f"GET {lp.PATH_VOTE_HISTORY}", FakeResponse(500, {"detail": "boom"}))

    assert session.check_vote_readiness(client) == "vote history could not be read"


# ── The full synchronized lifecycle ───────────────────────────────────────────


def run_cohort(plan, coordinator, clients, *, expected_threads=None):
    """Drive one virtual user per client through prepare_and_vote, concurrently."""
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(client):
        session = lp.VoterSession(plan, plan.pool.claim())
        try:
            outcome = lp.prepare_and_vote(session, client, coordinator)
        except Exception as exc:  # recorded, never retried
            outcome = f"error:{type(exc).__name__}"
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=worker, args=(c,)) for c in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any(t.is_alive() for t in threads), "a user never finished"
    return outcomes


def test_exactly_ten_votes_are_released_after_the_tenth_voter_is_ready(
    prepared, data_dir
):
    plan = plan_for(data_dir)
    plan.limit_users(10)
    coordinator = VoteCoordinator(10, timeout_seconds=10)
    clients = [ready_client(plan) for _ in range(10)]

    outcomes = run_cohort(plan, coordinator, clients)

    assert outcomes == ["accepted"] * 10
    assert coordinator.attempts == 10
    assert coordinator.accepted == 10
    assert coordinator.rejected == 0
    assert coordinator.aborted is False

    votes = [c for client in clients for c in client.calls_named(lp.NAME_CAST_VOTE)]
    assert len(votes) == 10
    # One ballot per client, and every one sent after the barrier released.
    for client in clients:
        assert len(client.calls_named(lp.NAME_CAST_VOTE)) == 1


def test_one_login_failure_causes_zero_vote_requests(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(10)
    coordinator = VoteCoordinator(10, timeout_seconds=5)

    clients = [ready_client(plan) for _ in range(10)]
    # Voter 7 cannot log in.
    clients[6].responses[f"POST {common.LOGIN_PATH}"] = [
        FakeResponse(401, {"detail": "Please provide a valid email and password"})
    ]

    run_cohort(plan, coordinator, clients)

    assert coordinator.aborted is True
    assert coordinator.attempts == 0
    assert coordinator.accepted == 0
    total_votes = sum(len(c.calls_named(lp.NAME_CAST_VOTE)) for c in clients)
    assert total_votes == 0


def test_one_ineligible_voter_causes_zero_vote_requests(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(10)
    coordinator = VoteCoordinator(10, timeout_seconds=5)

    clients = [ready_client(plan) for _ in range(10)]
    clients[3].responses[f"GET /elections/{plan.vote_election['election_id']}"] = [
        FakeResponse(403, {"detail": "not eligible"})
    ]

    run_cohort(plan, coordinator, clients)

    assert coordinator.aborted is True
    assert sum(len(c.calls_named(lp.NAME_CAST_VOTE)) for c in clients) == 0
    assert any("not eligible" in reason for _, reason in coordinator.failures)


def test_one_already_voted_voter_causes_zero_vote_requests(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(10)
    coordinator = VoteCoordinator(10, timeout_seconds=5)

    clients = [ready_client(plan) for _ in range(10)]
    clients[9].responses[f"GET {lp.PATH_VOTE_HISTORY}"] = [
        FakeResponse(
            200,
            [
                {
                    "id": "b1",
                    "election_id": plan.vote_election["election_id"],
                    "election_title": plan.vote_election["title"],
                    "receipt_code": "R",
                    "submitted_at": "2026-08-10T10:00:00",
                    "bulletin_status": "published",
                }
            ],
        )
    ]

    run_cohort(plan, coordinator, clients)

    assert coordinator.aborted is True
    assert sum(len(c.calls_named(lp.NAME_CAST_VOTE)) for c in clients) == 0
    assert any("already voted" in reason for _, reason in coordinator.failures)


def test_readiness_timeout_causes_zero_vote_requests(prepared, data_dir):
    """Only nine of the expected ten ever arrive, so nobody votes."""
    plan = plan_for(data_dir)
    plan.limit_users(10)
    coordinator = VoteCoordinator(10, timeout_seconds=0.3)

    clients = [ready_client(plan) for _ in range(9)]

    outcomes = run_cohort(plan, coordinator, clients)

    assert outcomes == ["aborted"] * 9
    assert coordinator.aborted is True
    assert coordinator.attempts == 0
    assert sum(len(c.calls_named(lp.NAME_CAST_VOTE)) for c in clients) == 0
    assert "readiness timeout" in (coordinator.summary().abort_reason or "")


def test_each_voter_is_allocated_once_across_the_cohort(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(10)
    coordinator = VoteCoordinator(10, timeout_seconds=10)
    clients = [ready_client(plan) for _ in range(10)]

    run_cohort(plan, coordinator, clients)

    assert len(coordinator.claimed) == 10
    assert len(coordinator.prepared) == 10
    assert len(set(coordinator.prepared)) == 10
    assert plan.pool.remaining == 0


def test_each_voter_attempts_at_most_one_vote(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(10)
    coordinator = VoteCoordinator(10, timeout_seconds=10)
    clients = [ready_client(plan) for _ in range(10)]

    run_cohort(plan, coordinator, clients)

    for client in clients:
        assert len(client.calls_named(lp.NAME_CAST_VOTE)) == 1
    assert coordinator.attempts == 10


def test_a_vote_exception_is_never_retried(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(1)
    coordinator = VoteCoordinator(1, timeout_seconds=5)

    class ExplodingClient(FakeLocustClient):
        vote_calls = 0

        def post(self, path, **kwargs):
            if str(path) == lp.PATH_VOTES:
                type(self).vote_calls += 1
                raise TimeoutError("connection timed out")
            return super().post(path, **kwargs)

    client = ExplodingClient()
    client.queue(f"POST {common.LOGIN_PATH}", FakeResponse(200, {"access_token": FAKE_TOKEN}))
    client.queue(
        f"GET /elections/{plan.vote_election['election_id']}",
        FakeResponse(200, live_election(plan)),
    )
    client.queue(f"GET {lp.PATH_VOTE_HISTORY}", FakeResponse(200, []))

    session = lp.VoterSession(plan, plan.pool.claim())

    with pytest.raises(TimeoutError):
        lp.prepare_and_vote(session, client, coordinator)

    assert ExplodingClient.vote_calls == 1
    assert session.vote_attempted is True
    assert coordinator.attempts == 1
    assert coordinator.rejected == 1
    # A second pass is refused outright rather than retried.
    with pytest.raises(lp.VoteBudgetExceeded):
        session.cast_vote(client)


def test_duplicate_vote_response_counts_as_failed_not_accepted(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(2)
    coordinator = VoteCoordinator(2, timeout_seconds=10)

    clients = [ready_client(plan) for _ in range(2)]
    clients[1].responses[f"POST {lp.PATH_VOTES}"] = [
        FakeResponse(400, {"detail": lp.DUPLICATE_VOTE_DETAIL})
    ]

    outcomes = run_cohort(plan, coordinator, clients)

    assert sorted(outcomes) == ["accepted", "rejected"]
    assert coordinator.attempts == 2
    assert coordinator.accepted == 1
    assert coordinator.rejected == 1
    assert clients[1].calls_named(lp.NAME_CAST_VOTE)[0].response.verdict == "failure"


def test_votes_use_the_normalised_request_name(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(2)
    coordinator = VoteCoordinator(2, timeout_seconds=10)
    clients = [ready_client(plan) for _ in range(2)]

    run_cohort(plan, coordinator, clients)

    for client in clients:
        names = [c.name for c in client.calls]
        assert lp.NAME_CAST_VOTE in names
        assert lp.NAME_CAST_VOTE == "POST /votes/"


def test_candidates_are_split_evenly_across_the_cohort(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(10)
    coordinator = VoteCoordinator(10, timeout_seconds=10)
    clients = [ready_client(plan) for _ in range(10)]

    run_cohort(plan, coordinator, clients)

    chosen = [
        c.json_body["candidate_id"]
        for client in clients
        for c in client.calls_named(lp.NAME_CAST_VOTE)
    ]
    candidate_ids = [c["id"] for c in plan.vote_election["candidates"]]

    assert sorted(set(chosen)) == sorted(candidate_ids)
    assert chosen.count(candidate_ids[0]) == 5
    assert chosen.count(candidate_ids[1]) == 5


def test_no_receipts_or_tokens_are_stored_on_the_coordinator(prepared, data_dir):
    plan = plan_for(data_dir)
    plan.limit_users(2)
    coordinator = VoteCoordinator(2, timeout_seconds=10)
    clients = [ready_client(plan) for _ in range(2)]

    run_cohort(plan, coordinator, clients)

    blob = repr(coordinator.summary()) + repr(coordinator.prepared) + repr(
        coordinator.failures
    )
    assert FAKE_TOKEN not in blob
    assert "RCPT" not in blob
    assert base_env()[common.ENV_VOTER_PASSWORD] not in blob


# ── Distributed execution is refused ──────────────────────────────────────────


class FakeOptions:
    def __init__(self, **kwargs):
        self.master = kwargs.get("master", False)
        self.worker = kwargs.get("worker", False)
        self.processes = kwargs.get("processes", None)
        self.num_users = kwargs.get("num_users", 10)
        self.host = kwargs.get("host", None)


class FakeEnvironment:
    """Enough of locust's Environment for the init hook. Has no client at all."""

    def __init__(self, parsed_options, host=None):
        self.parsed_options = parsed_options
        self.host = host
        self.runner = None


def import_locustfile(monkeypatch, data_dir, env):
    """Import the locustfile fresh under the given environment.

    ``importlib.reload`` reuses the module namespace, so classes defined by a
    previous scenario would linger and the "exactly one user class" assertion
    would be meaningless. Dropping it from sys.modules first guarantees a clean
    namespace.
    """
    pytest.importorskip("locust", reason="Locust is not installed in this environment")

    import importlib
    import sys

    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(common, "DATA_DIR", data_dir)

    sys.modules.pop("performance_tests.locustfile", None)
    return importlib.import_module("performance_tests.locustfile")


def test_distributed_master_is_refused():
    with pytest.raises(SafetyError, match="distributed master"):
        lp.refuse_distributed(FakeOptions(master=True))


def test_distributed_worker_is_refused():
    with pytest.raises(SafetyError, match="distributed worker"):
        lp.refuse_distributed(FakeOptions(worker=True))


@pytest.mark.parametrize("processes", [2, 4, 8, -1, 0])
def test_multiprocess_is_refused(processes):
    with pytest.raises(SafetyError, match="--processes"):
        lp.refuse_distributed(FakeOptions(processes=processes))


@pytest.mark.parametrize("processes", [None, 1])
def test_single_process_is_allowed(processes):
    lp.refuse_distributed(FakeOptions(processes=processes))


def test_missing_options_object_is_tolerated():
    lp.refuse_distributed(None)


# ── Selected-election verification (--vote-run-ready) ─────────────────────────


def verify_run(api, config, data_dir, silent, run):
    return verify.run_vote_run_verification(
        config, run, transport=api.transport(), data_dir=data_dir, write=silent
    )


def test_vote_run_ready_passes_for_a_pristine_run(prepared, api, config, data_dir, silent):
    report = verify_run(api, config, data_dir, silent, 2)

    assert report.ok, report.failures
    assert "READY" in report.render()


def test_vote_run_ready_ignores_votes_in_other_runs(
    prepared, api, config, data_dir, silent
):
    """Run 1 consumed; runs 2 and 3 must still verify as ready."""
    run_one = prepared["elections"][0]["election_id"]
    stored = api.elections[run_one]
    stored["voted"].update(stored["eligible"])  # all 50 voted in run 1

    assert verify_run(api, config, data_dir, silent, 2).ok
    assert verify_run(api, config, data_dir, silent, 3).ok


def test_vote_run_ready_rejects_votes_in_the_chosen_run(
    prepared, api, config, data_dir, silent
):
    run_two = prepared["elections"][1]["election_id"]
    stored = api.elections[run_two]
    stored["voted"].add(stored["eligible"][0])

    report = verify_run(api, config, data_dir, silent, 2)

    assert not report.ok
    assert any("no voter has voted" in f for f in report.failures)


def test_vote_run_ready_rejects_an_expired_run(prepared, api, config, data_dir, silent):
    run_one = prepared["elections"][0]["election_id"]
    api.elections[run_one]["response"]["end_date"] = "2020-01-01T00:00:00"

    report = verify_run(api, config, data_dir, silent, 1)

    assert not report.ok
    assert any("end time is in the future" in f or "expired" in f for f in report.failures)


def test_vote_run_ready_rejects_a_non_active_run(prepared, api, config, data_dir, silent):
    run_three = prepared["elections"][2]["election_id"]
    api.elections[run_three]["response"]["status"] = "completed"

    report = verify_run(api, config, data_dir, silent, 3)

    assert not report.ok
    assert any("status is active" in f for f in report.failures)


def test_vote_run_ready_makes_no_mutating_request(
    prepared, api, config, data_dir, silent
):
    api.requests.clear()

    verify_run(api, config, data_dir, silent, 1)

    assert not any(r.method in {"PUT", "PATCH", "DELETE"} for r in api.requests)
    assert {r.path for r in api.requests if r.method == "POST"} == {common.LOGIN_PATH}
    assert not any("/results" in r.path for r in api.requests)


def test_vote_run_ready_only_reads_the_selected_election(
    prepared, api, config, data_dir, silent
):
    other_ids = [e["election_id"] for e in prepared["elections"][1:]]
    api.requests.clear()

    verify_run(api, config, data_dir, silent, 1)

    for election_id in other_ids:
        assert not any(election_id in r.path for r in api.requests)


def test_vote_run_ready_refuses_an_invalid_run(prepared, api, config, data_dir, silent):
    with pytest.raises(ConfigError, match="must be one of"):
        verify_run(api, config, data_dir, silent, 4)


def test_vote_run_ready_refuses_production(prepared, api, data_dir, silent):
    production = common.load_config(
        base_env(**{common.ENV_BASE_URL: "https://api.example.com"}),
        require_voter_password=False,
    )
    # The `prepared` fixture built the manifest through this same fake API.
    api.requests.clear()

    with pytest.raises(SafetyError):
        verify_run(api, production, data_dir, silent, 1)

    assert api.requests == []


def test_full_verification_behaviour_is_unchanged(
    prepared, api, config, data_dir, silent
):
    """The narrow mode must not weaken the full check: run 1 consumed => NOT READY."""
    full_before = verify.run_verification(
        config, transport=api.transport(), data_dir=data_dir, write=silent
    )
    assert full_before.ok, full_before.failures

    run_one = prepared["elections"][0]["election_id"]
    stored = api.elections[run_one]
    stored["voted"].add(stored["eligible"][0])

    full_after = verify.run_verification(
        config, transport=api.transport(), data_dir=data_dir, write=silent
    )

    assert not full_after.ok
    assert any("no voter has voted" in f for f in full_after.failures)
    # …while the narrow mode still passes runs 2 and 3.
    assert verify_run(api, config, data_dir, silent, 2).ok


def test_vote_run_ready_is_exposed_on_the_cli():
    parser = verify.build_parser()

    assert parser.parse_args(["--vote-run-ready", "2"]).vote_run_ready == 2
    assert parser.parse_args([]).vote_run_ready is None

    with pytest.raises(SystemExit):
        parser.parse_args(["--vote-run-ready", "4"])


# ── No network ────────────────────────────────────────────────────────────────


def test_vote_coordinator_imports_no_network_library():
    import inspect

    source = inspect.getsource(vc)

    for forbidden in ("import requests", "import httpx", "import socket", "import gevent"):
        assert forbidden not in source


def test_the_locust_adapter_imports(monkeypatch, prepared, data_dir):
    """The real locustfile must import and define only the vote user.

    Skipped until `pip install -r performance_tests/requirements.txt` is run.
    """
    module = import_locustfile(monkeypatch, data_dir, vote_env())

    from locust import HttpUser

    user_classes = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, HttpUser)
        and not getattr(obj, "abstract", False)
    ]

    assert len(user_classes) == 1
    assert user_classes[0].__name__ == "VoterVoteUser"


def test_the_adapter_refuses_a_run_user_count_mismatch(monkeypatch, prepared, data_dir):
    """Election run 1 with --users 50 must stop the process before spawning."""
    module = import_locustfile(monkeypatch, data_dir, vote_env(run="1"))

    environment = FakeEnvironment(FakeOptions(num_users=50))

    with pytest.raises(SystemExit):
        module._validate_runtime_target(environment)


def test_the_adapter_refuses_distributed_vote_execution(monkeypatch, prepared, data_dir):
    module = import_locustfile(monkeypatch, data_dir, vote_env(run="1"))

    for options in (
        FakeOptions(num_users=10, master=True),
        FakeOptions(num_users=10, worker=True),
        FakeOptions(num_users=10, processes=4),
    ):
        with pytest.raises(SystemExit):
            module._validate_runtime_target(FakeEnvironment(options))


def test_the_adapter_builds_a_coordinator_for_the_matching_cohort(
    monkeypatch, prepared, data_dir
):
    module = import_locustfile(monkeypatch, data_dir, vote_env(run="2"))

    module._validate_runtime_target(FakeEnvironment(FakeOptions(num_users=25)))

    assert module.COORDINATOR is not None
    assert module.COORDINATOR.expected == 25
    assert module.COORDINATOR.timeout_seconds == 600.0
    assert len(module.PLAN.pool) == 25


def test_the_adapter_refuses_a_host_that_is_not_the_validated_target(
    monkeypatch, prepared, data_dir
):
    module = import_locustfile(monkeypatch, data_dir, vote_env(run="1"))

    options = FakeOptions(num_users=10, host="https://api.example.com")

    with pytest.raises(SystemExit):
        module._validate_runtime_target(FakeEnvironment(options, host=options.host))


def test_the_adapter_pins_locust_to_the_validated_target(monkeypatch, prepared, data_dir):
    module = import_locustfile(monkeypatch, data_dir, vote_env(run="1"))
    environment = FakeEnvironment(FakeOptions(num_users=10))

    module._validate_runtime_target(environment)

    assert environment.host == module.PLAN.base_url
