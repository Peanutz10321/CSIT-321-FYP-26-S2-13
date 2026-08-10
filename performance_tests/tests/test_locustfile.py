"""Unit tests for the Locust load plan and virtual-user behaviour.

Everything here runs against ``FakeLocustClient``, an in-memory stand-in for
Locust's ``HttpSession`` that records requests and the success/failure verdict
each one was given. It has no transport, no socket and no ``requests`` import, so
these tests are structurally incapable of contacting a network.

``load_plan`` itself imports neither ``locust`` nor ``requests``; a test below
asserts that, because it is what keeps this suite runnable (and offline) whether
or not Locust is installed.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from performance_tests import common, load_plan as lp, setup_performance_data as setup
from performance_tests.common import ConfigError, ManifestError, SafetyError

from .conftest import (
    BATCH,
    FAKE_TOKEN,
    PRODUCTION_URL,
    STAGING_URL,
    VOTER_PASSWORD,
    base_env,
)


# ── A fake Locust HttpSession ─────────────────────────────────────────────────


@dataclass
class FakeResponse:
    status_code: int
    body: Any = None
    verdict: str | None = None
    failure_message: str | None = None

    def json(self) -> Any:
        if isinstance(self.body, str):
            return json.loads(self.body)  # raises for malformed bodies
        if self.body is None:
            raise ValueError("no JSON body")
        return self.body

    def success(self) -> None:
        self.verdict = "success"

    def failure(self, message: str) -> None:
        self.verdict = "failure"
        self.failure_message = str(message)


@dataclass
class RecordedCall:
    method: str
    path: str
    name: str | None
    headers: dict[str, str]
    json_body: Any
    response: FakeResponse


class _ResponseContext:
    def __init__(self, response: FakeResponse):
        self._response = response

    def __enter__(self) -> FakeResponse:
        return self._response

    def __exit__(self, *exc_info) -> bool:
        return False


@dataclass
class FakeLocustClient:
    """Duck-typed stand-in for locust's HttpSession. No network of any kind."""

    responses: dict[str, list[FakeResponse]] = field(default_factory=dict)
    default: FakeResponse | None = None
    calls: list[RecordedCall] = field(default_factory=list)

    def queue(self, key: str, *responses: FakeResponse) -> None:
        self.responses.setdefault(key, []).extend(responses)

    def get(self, path, name=None, headers=None, catch_response=False, **kwargs):
        return self._call("GET", path, name, headers, None)

    def post(self, path, json=None, name=None, headers=None, catch_response=False, **kw):
        return self._call("POST", path, name, headers, json)

    def _call(self, method, path, name, headers, json_body):
        key = f"{method} {path}"
        queued = self.responses.get(key)
        if queued:
            response = queued.pop(0)
        elif self.default is not None:
            response = FakeResponse(self.default.status_code, self.default.body)
        else:
            raise AssertionError(f"FakeLocustClient has no response for {key}")

        self.calls.append(
            RecordedCall(
                method=method,
                path=str(path),
                name=name,
                headers=dict(headers or {}),
                json_body=json_body,
                response=response,
            )
        )
        return _ResponseContext(response)

    # helpers
    @property
    def names(self) -> list[str]:
        return [call.name for call in self.calls]

    @property
    def verdicts(self) -> list[str | None]:
        return [call.response.verdict for call in self.calls]

    def calls_named(self, name: str) -> list[RecordedCall]:
        return [call for call in self.calls if call.name == name]


# ── Building a manifest to plan against ───────────────────────────────────────


@pytest.fixture
def prepared(api, config, data_dir, silent):
    """A complete, verified-shaped manifest produced by the real setup flow."""
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


def read_env(**overrides):
    env = base_env(**{lp.ENV_SCENARIO: "read"})
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


def vote_env(**overrides):
    env = base_env(
        **{
            lp.ENV_SCENARIO: "vote",
            lp.ENV_VOTE_LOAD_ALLOWED: "true",
            lp.ENV_VOTE_ELECTION_RUN: "1",
        }
    )
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


def build(env, data_dir, **kwargs):
    return lp.build_plan(env, data_dir=data_dir, **kwargs)


def session_for(plan, index=0):
    voter = plan.pool.claim()
    assert voter.index == index
    session = lp.VoterSession(plan, voter)
    session._token = FAKE_TOKEN  # skip the login round-trip
    return session


# ── Scenario selection ────────────────────────────────────────────────────────


def test_missing_scenario_is_refused(prepared, data_dir):
    env = read_env()
    del env[lp.ENV_SCENARIO]

    with pytest.raises(ConfigError, match="PERF_SCENARIO must be set"):
        build(env, data_dir)


@pytest.mark.parametrize("value", ["Read", "READ", "vote ", "browse", "", "read,vote"])
def test_invalid_scenario_is_refused(prepared, data_dir, value):
    with pytest.raises(ConfigError):
        build(read_env(**{lp.ENV_SCENARIO: value}), data_dir)


def test_read_scenario_builds_a_plan(prepared, data_dir):
    plan = build(read_env(), data_dir)

    assert plan.scenario == lp.SCENARIO_READ
    assert plan.vote_election is None
    assert len(plan.voters) == 50
    assert len(plan.election_ids) == 3
    assert (plan.min_wait, plan.max_wait) == (1.0, 3.0)


# ── Target safety ─────────────────────────────────────────────────────────────


def test_production_target_is_refused(prepared, data_dir):
    env = read_env(**{common.ENV_BASE_URL: PRODUCTION_URL})

    with pytest.raises(SafetyError, match="same target"):
        build(env, data_dir)


def test_non_https_target_is_refused(prepared, data_dir):
    env = read_env(**{common.ENV_BASE_URL: "http://staging-api.example.com"})

    with pytest.raises(SafetyError, match="must be HTTPS"):
        build(env, data_dir)


def test_target_without_staging_marker_is_refused(prepared, data_dir):
    env = read_env(**{common.ENV_BASE_URL: "https://evoting-api.example.com"})

    with pytest.raises(SafetyError, match="does not identify itself"):
        build(env, data_dir)


def test_locust_host_mismatch_is_refused(prepared, data_dir):
    with pytest.raises(SafetyError, match=r"--host .* does not match"):
        build(read_env(), data_dir, host="https://performance-api.other.example.com")


def test_locust_host_pointing_at_production_is_refused(prepared, data_dir):
    with pytest.raises(SafetyError, match=r"--host"):
        build(read_env(), data_dir, host=PRODUCTION_URL)


def test_locust_host_matching_after_normalization_is_accepted(prepared, data_dir):
    plan = build(read_env(), data_dir, host="https://Staging-API.example.com:443/")

    assert plan.base_url == STAGING_URL


def test_empty_locust_host_is_refused(prepared, data_dir):
    with pytest.raises(SafetyError, match="empty --host"):
        build(read_env(), data_dir, host="   ")


def test_locust_host_with_malformed_port_is_refused(prepared, data_dir):
    with pytest.raises(SafetyError, match="invalid port"):
        build(read_env(), data_dir, host="https://staging-api.example.com:abc")


# ── Manifest ──────────────────────────────────────────────────────────────────


def test_missing_manifest_is_refused(data_dir):
    with pytest.raises(ManifestError, match="No manifest at"):
        build(read_env(), data_dir)


def test_incomplete_manifest_is_refused(prepared, data_dir):
    """A half-prepared data set is not something to load test."""
    manifest = prepared
    manifest["voters"].pop()
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))

    with pytest.raises(ManifestError, match="49 voters"):
        build(read_env(), data_dir)


def test_manifest_from_another_deployment_is_refused(prepared, data_dir):
    manifest = prepared
    manifest["base_url"] = "https://performance-api.other.example.com"
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))

    with pytest.raises(ManifestError, match="two deployments"):
        build(read_env(), data_dir)


# ── User count and voter allocation ───────────────────────────────────────────


@pytest.mark.parametrize("users", [51, 60, 100, 1000])
def test_more_than_fifty_users_is_refused(users):
    with pytest.raises(SafetyError, match="only 50 voter accounts"):
        lp.check_user_count(users)


@pytest.mark.parametrize("users", [1, 10, 25, 50])
def test_commissioned_user_counts_are_accepted(users):
    assert lp.check_user_count(users) == users


def test_zero_users_is_refused():
    with pytest.raises(ConfigError, match="at least 1"):
        lp.check_user_count(0)


def test_plan_refuses_to_be_limited_above_fifty(prepared, data_dir):
    plan = build(read_env(), data_dir)

    with pytest.raises(SafetyError, match="only 50 voter accounts"):
        plan.limit_users(51)


def test_each_voter_is_allocated_to_exactly_one_user(prepared, data_dir):
    plan = build(read_env(), data_dir)

    claimed = [plan.pool.claim() for _ in range(50)]

    usernames = [voter.username for voter in claimed]
    assert len(set(usernames)) == 50
    assert usernames == [common.voter_username(i, BATCH) for i in range(1, 51)]
    assert [voter.index for voter in claimed] == list(range(50))


def test_pool_is_exhausted_rather_than_reissuing_a_voter(prepared, data_dir):
    plan = build(read_env(), data_dir)
    for _ in range(50):
        plan.pool.claim()

    assert plan.pool.remaining == 0
    with pytest.raises(lp.PoolExhausted, match="already in use"):
        plan.pool.claim()


def test_concurrent_allocation_never_hands_out_a_duplicate(prepared, data_dir):
    """Locust spawns from many greenlets, so allocation must be atomic."""
    plan = build(read_env(), data_dir)
    claimed: list[lp.ClaimedVoter] = []
    lock = threading.Lock()
    start = threading.Event()

    def worker():
        start.wait()
        try:
            voter = plan.pool.claim()
        except lp.PoolExhausted:
            return
        with lock:
            claimed.append(voter)

    threads = [threading.Thread(target=worker) for _ in range(80)]
    for thread in threads:
        thread.start()
    start.set()
    for thread in threads:
        thread.join()

    assert len(claimed) == 50
    assert len({voter.username for voter in claimed}) == 50
    assert len({voter.index for voter in claimed}) == 50


def test_limit_users_caps_the_pool_at_the_commissioned_size(prepared, data_dir):
    """Ten users must consume ten ballots, even if Locust replaces stopped users."""
    plan = build(vote_env(), data_dir)
    plan.limit_users(10)

    assert len(plan.pool) == 10
    for _ in range(10):
        plan.pool.claim()
    with pytest.raises(lp.PoolExhausted):
        plan.pool.claim()


# ── Login ─────────────────────────────────────────────────────────────────────


def test_successful_login_stores_the_token_in_memory_only(prepared, data_dir):
    plan = build(read_env(), data_dir)
    voter = plan.pool.claim()
    session = lp.VoterSession(plan, voter)
    client = FakeLocustClient()
    client.queue(
        f"POST {common.LOGIN_PATH}",
        FakeResponse(200, {"access_token": FAKE_TOKEN, "token_type": "bearer"}),
    )

    assert session.login(client) is True
    assert session.authenticated
    assert session.headers == {"Authorization": f"Bearer {FAKE_TOKEN}"}
    assert client.verdicts == ["success"]
    assert client.names == [lp.NAME_LOGIN]


def test_login_sends_the_voter_email_and_password(prepared, data_dir):
    plan = build(read_env(), data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    client = FakeLocustClient()
    client.queue(f"POST {common.LOGIN_PATH}", FakeResponse(200, {"access_token": "t"}))

    session.login(client)

    body = client.calls[0].json_body
    assert body["email"] == common.voter_email(1, BATCH)
    assert body["password"] == VOTER_PASSWORD


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, {"detail": "Please provide a valid email and password"}),
        (403, {"detail": "Please provide a valid email and password"}),
        (500, {"detail": "boom"}),
        (200, {"token_type": "bearer"}),  # no access_token
        (200, "{not json"),  # malformed body
    ],
)
def test_login_failure_is_recorded_and_leaves_the_user_unauthenticated(
    prepared, data_dir, status, body
):
    plan = build(read_env(), data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    client = FakeLocustClient()
    client.queue(f"POST {common.LOGIN_PATH}", FakeResponse(status, body))

    assert session.login(client) is False
    assert session.authenticated is False
    assert client.verdicts == ["failure"]


def test_login_failure_message_never_contains_the_password(prepared, data_dir):
    plan = build(read_env(), data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())
    client = FakeLocustClient()
    client.queue(f"POST {common.LOGIN_PATH}", FakeResponse(401, {"detail": "nope"}))

    session.login(client)

    message = client.calls[0].response.failure_message or ""
    assert VOTER_PASSWORD not in message
    assert "password" not in message.lower()


# ── Read scenario ─────────────────────────────────────────────────────────────


def test_every_read_request_carries_the_bearer_token(prepared, data_dir):
    plan = build(read_env(), data_dir)
    session = session_for(plan)
    client = FakeLocustClient()

    client.queue(f"GET {lp.PATH_ACTIVE_ELECTIONS}", FakeResponse(200, []))
    client.queue(f"GET {lp.PATH_ELECTION_HISTORY}", FakeResponse(200, []))
    client.queue(f"GET {lp.PATH_VOTE_HISTORY}", FakeResponse(200, []))
    client.queue(f"GET {lp.PATH_PROFILE}", FakeResponse(200, {"email": session.voter.email}))
    election_id = plan.election_ids[0]
    client.queue(f"GET /elections/{election_id}", FakeResponse(200, {"id": election_id}))

    session.read_active_elections(client)
    session.read_election_history(client)
    session.read_vote_history(client)
    session.read_profile(client)
    session.read_election_detail(client, election_id)

    assert len(client.calls) == 5
    for call in client.calls:
        assert call.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
    assert client.verdicts == ["success"] * 5


def test_unauthenticated_session_cannot_build_headers(prepared, data_dir):
    plan = build(read_env(), data_dir)
    session = lp.VoterSession(plan, plan.pool.claim())

    with pytest.raises(lp.PerfError, match="Not authenticated"):
        _ = session.headers


def test_election_detail_uses_a_normalised_request_name(prepared, data_dir):
    """Ids must not fragment the metrics into one row per election."""
    plan = build(read_env(), data_dir)
    session = session_for(plan)
    client = FakeLocustClient()

    for election_id in plan.election_ids:
        client.queue(f"GET /elections/{election_id}", FakeResponse(200, {"id": election_id}))
        session.read_election_detail(client, election_id)

    assert client.names == [lp.NAME_ELECTION_DETAIL] * 3
    assert lp.NAME_ELECTION_DETAIL == "GET /elections/[id]"
    # The real id is still in the URL that was actually requested.
    assert [call.path for call in client.calls] == [
        f"/elections/{eid}" for eid in plan.election_ids
    ]


def test_vote_detail_uses_a_normalised_request_name(prepared, data_dir):
    plan = build(read_env(), data_dir)
    session = session_for(plan)
    client = FakeLocustClient()
    client.queue("GET /votes/abc-123", FakeResponse(200, {"receipt_code": "RCPT-1"}))

    session.read_vote_detail(client, "abc-123")

    assert client.names == [lp.NAME_VOTE_DETAIL]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 502])
def test_unexpected_read_status_is_a_failure(prepared, data_dir, status):
    plan = build(read_env(), data_dir)
    session = session_for(plan)
    client = FakeLocustClient()
    client.queue(f"GET {lp.PATH_ACTIVE_ELECTIONS}", FakeResponse(status, {"detail": "x"}))

    assert session.read_active_elections(client) == []
    assert client.verdicts == ["failure"]


@pytest.mark.parametrize(
    "body",
    [
        {"not": "a list"},
        "{malformed",
        None,
    ],
)
def test_malformed_read_body_is_a_failure(prepared, data_dir, body):
    plan = build(read_env(), data_dir)
    session = session_for(plan)
    client = FakeLocustClient()
    client.queue(f"GET {lp.PATH_ACTIVE_ELECTIONS}", FakeResponse(200, body))

    assert session.read_active_elections(client) == []
    assert client.verdicts == ["failure"]


def test_profile_for_the_wrong_account_is_a_failure(prepared, data_dir):
    """Catches a token/voter mix-up, which would invalidate the whole run."""
    plan = build(read_env(), data_dir)
    session = session_for(plan)
    client = FakeLocustClient()
    client.queue(f"GET {lp.PATH_PROFILE}", FakeResponse(200, {"email": "someone@test.com"}))

    assert session.read_profile(client) is None
    assert client.verdicts == ["failure"]


def test_read_scenario_never_touches_the_results_endpoint(prepared, data_dir):
    """GET /results/... is the only trigger for finalization, so it is excluded."""
    plan = build(read_env(), data_dir)
    session = session_for(plan)
    client = FakeLocustClient(default=FakeResponse(200, []))

    session.read_active_elections(client)
    session.read_election_history(client)
    session.read_vote_history(client)

    assert not any("/results" in call.path for call in client.calls)


# ── Vote scenario: arming ─────────────────────────────────────────────────────


def test_vote_mode_is_disarmed_by_default(prepared, data_dir):
    env = vote_env()
    del env[lp.ENV_VOTE_LOAD_ALLOWED]

    with pytest.raises(SafetyError, match="Vote load is disabled"):
        build(env, data_dir)


@pytest.mark.parametrize("value", ["True", "TRUE", "1", "yes", "y", " true", "false"])
def test_vote_arming_requires_exact_lowercase_true(prepared, data_dir, value):
    with pytest.raises(SafetyError, match="Vote load is disabled"):
        build(vote_env(**{lp.ENV_VOTE_LOAD_ALLOWED: value}), data_dir)


def test_read_scenario_does_not_require_the_vote_flag(prepared, data_dir):
    env = read_env()
    env.pop(lp.ENV_VOTE_LOAD_ALLOWED, None)

    plan = build(env, data_dir)

    assert plan.scenario == lp.SCENARIO_READ


@pytest.mark.parametrize("value", ["0", "4", "-1", "one", "", "1.5", "01x"])
def test_invalid_election_run_is_refused(prepared, data_dir, value):
    with pytest.raises(ConfigError):
        build(vote_env(**{lp.ENV_VOTE_ELECTION_RUN: value}), data_dir)


@pytest.mark.parametrize("run", [1, 2, 3])
def test_each_valid_election_run_resolves(prepared, data_dir, run):
    plan = build(vote_env(**{lp.ENV_VOTE_ELECTION_RUN: str(run)}), data_dir)

    assert plan.vote_election["run"] == run
    assert plan.vote_election["title"] == common.election_title(BATCH, run)
    assert plan.vote_election["election_id"] == prepared["elections"][run - 1]["election_id"]


def test_completed_election_is_refused(prepared, data_dir):
    manifest = prepared
    manifest["elections"][0]["status"] = "completed"
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))

    with pytest.raises(SafetyError, match="not 'active'"):
        build(vote_env(), data_dir)


def test_expired_election_is_refused(prepared, data_dir):
    manifest = prepared
    manifest["elections"][0]["end_date"] = "2020-01-01T00:00:00"
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))

    with pytest.raises(SafetyError, match="Refusing to vote in an expired election"):
        build(vote_env(), data_dir)


def test_missing_election_entry_is_refused(prepared, data_dir):
    manifest = prepared
    manifest["elections"] = manifest["elections"][:2]
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))

    with pytest.raises(ManifestError, match="2 elections"):
        build(vote_env(**{lp.ENV_VOTE_ELECTION_RUN: "3"}), data_dir)


def test_preflight_refuses_an_election_that_closed_since_setup(prepared, data_dir, api):
    """The manifest is a snapshot; the live status is re-read before the run."""
    plan = build(vote_env(), data_dir)
    election_id = plan.vote_election["election_id"]
    api.elections[election_id]["response"]["status"] = "completed"

    with pytest.raises(SafetyError, match="not 'active'"):
        lp.preflight_vote_election(plan, transport=api.transport())


def test_preflight_accepts_a_live_active_election(prepared, data_dir, api):
    plan = build(vote_env(), data_dir)

    body = lp.preflight_vote_election(plan, transport=api.transport())

    assert body["status"] == "active"


def test_preflight_makes_no_mutating_request(prepared, data_dir, api):
    plan = build(vote_env(), data_dir)
    api.requests.clear()

    lp.preflight_vote_election(plan, transport=api.transport())

    assert {call.method for call in api.requests} <= {"GET", "POST"}
    assert [c.path for c in api.requests if c.method == "POST"] == [common.LOGIN_PATH]
    assert not any("/results" in call.path for call in api.requests)


# ── Vote scenario: casting ────────────────────────────────────────────────────


def _vote_client(status=201, body=None):
    client = FakeLocustClient()
    client.queue(
        f"POST {lp.PATH_VOTES}",
        FakeResponse(status, body if body is not None else {"receipt_code": "RCPT-ABC"}),
    )
    return client


def test_a_successful_vote_sends_the_expected_payload(prepared, data_dir):
    plan = build(vote_env(), data_dir)
    session = session_for(plan)
    client = _vote_client()

    assert session.cast_vote(client) is True

    call = client.calls[0]
    assert call.name == lp.NAME_CAST_VOTE
    assert call.path == "/votes/"
    assert call.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
    assert call.json_body == {
        "election_id": plan.vote_election["election_id"],
        "candidate_id": plan.vote_election["candidates"][0]["id"],
    }
    assert client.verdicts == ["success"]


def test_exactly_one_vote_attempt_per_voter(prepared, data_dir):
    plan = build(vote_env(), data_dir)
    session = session_for(plan)
    client = _vote_client()

    session.cast_vote(client)

    assert session.vote_attempted is True
    with pytest.raises(lp.VoteBudgetExceeded, match="already attempted"):
        session.cast_vote(client)

    assert len(client.calls_named(lp.NAME_CAST_VOTE)) == 1


def test_a_failed_vote_is_never_retried(prepared, data_dir):
    plan = build(vote_env(), data_dir)
    session = session_for(plan)
    client = _vote_client(status=500, body={"detail": "boom"})

    assert session.cast_vote(client) is False

    with pytest.raises(lp.VoteBudgetExceeded):
        session.cast_vote(client)
    assert len(client.calls) == 1


def test_an_uncertain_vote_is_never_retried(prepared, data_dir):
    """A transport-level error leaves the attempt flag set: the server may have it."""
    plan = build(vote_env(), data_dir)
    session = session_for(plan)

    class ExplodingClient(FakeLocustClient):
        def post(self, *args, **kwargs):
            raise TimeoutError("connection timed out")

    client = ExplodingClient()

    with pytest.raises(TimeoutError):
        session.cast_vote(client)

    # The flag was set before the request was sent, so no retry is possible.
    assert session.vote_attempted is True
    with pytest.raises(lp.VoteBudgetExceeded):
        session.cast_vote(FakeLocustClient(default=FakeResponse(201, {"receipt_code": "x"})))


def test_duplicate_vote_response_is_recorded_as_a_failure(prepared, data_dir):
    plan = build(vote_env(), data_dir)
    session = session_for(plan)
    client = _vote_client(status=400, body={"detail": lp.DUPLICATE_VOTE_DETAIL})

    assert session.cast_vote(client) is False
    assert client.verdicts == ["failure"]
    assert "duplicate vote" in (client.calls[0].response.failure_message or "")


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, {"detail": "Only active elections can be voted in"}),
        (400, {"detail": "Election is not currently within its voting period"}),
        (403, {"detail": "You are not eligible to vote in this election"}),
        (404, {"detail": "Election not found"}),
        (500, {"detail": "Election encryption keys are not initialized"}),
        (201, {"no": "receipt"}),
        (201, "{malformed"),
    ],
)
def test_unexpected_vote_outcomes_are_failures(prepared, data_dir, status, body):
    plan = build(vote_env(), data_dir)
    session = session_for(plan)
    client = _vote_client(status=status, body=body)

    assert session.cast_vote(client) is False
    assert client.verdicts == ["failure"]


def test_candidate_selection_is_deterministic_and_even(prepared, data_dir):
    plan = build(vote_env(), data_dir)
    candidate_ids = [c["id"] for c in plan.vote_election["candidates"]]

    chosen = [plan.candidate_for(index)["id"] for index in range(50)]

    assert chosen[0] == candidate_ids[0]
    assert chosen[1] == candidate_ids[1]
    assert chosen.count(candidate_ids[0]) == 25
    assert chosen.count(candidate_ids[1]) == 25
    # Reproducible: the same plan yields the same assignment every time.
    assert chosen == [plan.candidate_for(index)["id"] for index in range(50)]


def test_ten_users_cast_exactly_ten_distinct_ballots(prepared, data_dir):
    """The shape of the commissioned election-1 run, end to end and offline."""
    plan = build(vote_env(), data_dir)
    plan.limit_users(10)

    client = FakeLocustClient(default=FakeResponse(201, {"receipt_code": "RCPT"}))
    voted: list[str] = []

    while True:
        try:
            voter = plan.pool.claim()
        except lp.PoolExhausted:
            break
        session = lp.VoterSession(plan, voter)
        session._token = FAKE_TOKEN
        assert session.cast_vote(client) is True
        voted.append(voter.username)

    assert len(voted) == 10
    assert len(set(voted)) == 10
    assert len(client.calls_named(lp.NAME_CAST_VOTE)) == 10


# ── Secret hygiene ────────────────────────────────────────────────────────────


def test_plan_repr_does_not_leak_the_voter_password(prepared, data_dir):
    plan = build(read_env(), data_dir)

    assert VOTER_PASSWORD not in repr(plan)
    assert VOTER_PASSWORD not in str(plan)
    assert "voter_password" not in repr(plan)


def test_session_repr_does_not_leak_the_token(prepared, data_dir):
    plan = build(read_env(), data_dir)
    session = session_for(plan)

    assert FAKE_TOKEN not in repr(session)
    assert VOTER_PASSWORD not in repr(session)


def test_describe_plan_contains_no_secrets(prepared, data_dir):
    read_summary = lp.describe_plan(build(read_env(), data_dir), users=10)
    vote_summary = lp.describe_plan(build(vote_env(), data_dir), users=10)

    for summary in (read_summary, vote_summary):
        assert VOTER_PASSWORD not in summary
        assert FAKE_TOKEN not in summary
        assert "password" not in summary.lower()
        assert "Bearer" not in summary

    assert "VOTING IS ARMED" in vote_summary
    assert "Read-only scenario" in read_summary


def test_load_test_writes_no_files(prepared, data_dir, tmp_path):
    """Building a plan and casting votes touches nothing on disk."""
    before = {p: p.stat().st_mtime_ns for p in data_dir.rglob("*") if p.is_file()}

    plan = build(vote_env(), data_dir)
    session = session_for(plan)
    session.cast_vote(FakeLocustClient(default=FakeResponse(201, {"receipt_code": "x"})))

    after = {p: p.stat().st_mtime_ns for p in data_dir.rglob("*") if p.is_file()}
    assert before == after


# ── No network is reachable from these tests ──────────────────────────────────


def test_load_plan_imports_neither_locust_nor_requests():
    """Keeps this suite offline and runnable without Locust installed."""
    import inspect

    source = inspect.getsource(lp)

    assert "import locust" not in source
    assert "import requests" not in source
    assert "from locust" not in source
    assert "from requests" not in source


def test_the_fake_client_has_no_transport():
    """The read/vote behaviour tests cannot open a socket even in principle."""
    client = FakeLocustClient()

    assert not hasattr(client, "transport")
    assert not hasattr(client, "send")
    assert type(client).__module__ == __name__


def test_preflight_client_cannot_be_built_without_a_mock_transport(prepared, data_dir):
    """The autouse conftest guard also covers the one real client this module uses."""
    plan = build(vote_env(), data_dir)

    with pytest.raises(AssertionError, match="never touch the network"):
        lp.preflight_vote_election(plan)


def test_preflight_client_is_read_only(prepared, data_dir, api):
    """Its transport-level guard blocks a mutating request outright."""
    plan = build(vote_env(), data_dir)

    with common.build_client(
        plan.base_url, transport=api.transport(), read_only=True
    ) as client:
        with pytest.raises(common.ReadOnlyViolationError):
            client.post(lp.PATH_VOTES, json={})


# ── Locust bindings, when Locust is installed ─────────────────────────────────


def test_locustfile_imports_and_defines_one_user_class(monkeypatch, prepared, data_dir):
    """Skipped until `pip install -r performance_tests/requirements.txt` is run.

    Guards the adapter itself: the module must import, expose exactly one
    HttpUser subclass, and pick the one the scenario asked for.
    """
    pytest.importorskip("locust", reason="Locust is not installed in this environment")

    import importlib
    import sys

    from locust import HttpUser

    for key, value in read_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(common, "DATA_DIR", data_dir)

    # Dropped from sys.modules rather than reloaded: reload reuses the module
    # namespace, so a user class defined by another scenario's import would
    # linger and make the "exactly one" assertion meaningless.
    sys.modules.pop("performance_tests.locustfile", None)
    module = importlib.import_module("performance_tests.locustfile")

    user_classes = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, HttpUser)
        and not getattr(obj, "abstract", False)
    ]

    assert len(user_classes) == 1
    assert user_classes[0].__name__ == "VoterReadUser"
