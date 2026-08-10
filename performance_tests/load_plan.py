"""Scenario resolution, target safety, voter allocation and request behaviour.

This is the whole load test *except* the Locust bindings. It deliberately does
not import ``locust`` (or ``requests``), for two reasons:

* the unit tests can exercise every behaviour without Locust installed, and
  without anything in the import graph that can open a socket;
* the Locust-specific part in ``locustfile.py`` stays a thin adapter, so what is
  untested there is glue rather than logic.

The HTTP calls take a *client* argument that is duck-typed to Locust's
``HttpSession``: ``get``/``post`` accepting ``name=`` and ``catch_response=True``
and returning a context manager whose value has ``status_code``, ``json()``,
``success()`` and ``failure()``. The tests pass a recording fake; Locust passes
the real session.

Nothing here prints or persists a password or a token. The JWT lives on a
``VoterSession`` instance for the lifetime of the virtual user and nowhere else.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from performance_tests import common
from performance_tests.common import (
    ConfigError,
    ManifestError,
    PerfError,
    SafetyError,
)


# ── Scenarios ─────────────────────────────────────────────────────────────────

SCENARIO_READ = "read"
SCENARIO_VOTE = "vote"
VALID_SCENARIOS = (SCENARIO_READ, SCENARIO_VOTE)

ENV_SCENARIO = "PERF_SCENARIO"
ENV_VOTE_LOAD_ALLOWED = "PERF_VOTE_LOAD_ALLOWED"
ENV_VOTE_ELECTION_RUN = "PERF_VOTE_ELECTION_RUN"
ENV_MIN_WAIT = "PERF_MIN_WAIT_SECONDS"
ENV_MAX_WAIT = "PERF_MAX_WAIT_SECONDS"
ENV_VOTE_READY_TIMEOUT = "PERF_VOTE_READY_TIMEOUT_SECONDS"

# One prepared voter per virtual user, and there are exactly fifty of them.
MAX_USERS = common.VOTER_COUNT

# Documented defaults for the read scenario's think time, in seconds.
DEFAULT_MIN_WAIT = 1.0
DEFAULT_MAX_WAIT = 3.0

VALID_ELECTION_RUNS = (1, 2, 3)

# The commissioned vote runs. Each election receives exactly one cohort, once,
# and the pairing is fixed: a run/user-count mismatch is refused before spawning
# so a mis-typed --users cannot spend ballots at the wrong concurrency level.
VOTE_RUN_USER_COUNTS: dict[int, int] = {1: 10, 2: 25, 3: 50}

# How long a prepared voter will hold at the barrier before the run is abandoned.
# Must comfortably exceed the spawn time of the largest cohort: 50 voters at the
# documented --spawn-rate 0.2 take 250s to spawn, plus login and readiness reads
# for each, so the default leaves a wide margin.
DEFAULT_VOTE_READY_TIMEOUT = 600.0


# ── Normalised Locust request names ───────────────────────────────────────────
#
# Locust groups statistics by request name. Passing the raw URL would create one
# row per election id and per ballot id, which fragments the metrics into
# useless single-sample buckets. Every id-bearing path is reported under a fixed
# label instead.

NAME_LOGIN = "POST /auth/login"
NAME_ACTIVE_ELECTIONS = "GET /elections/active"
NAME_ELECTION_HISTORY = "GET /elections/history"
NAME_ELECTION_DETAIL = "GET /elections/[id]"
NAME_VOTE_HISTORY = "GET /votes/history"
NAME_VOTE_DETAIL = "GET /votes/[id]"
NAME_PROFILE = "GET /users/me"
NAME_CAST_VOTE = "POST /votes/"

# Backend paths, taken from the routers in backend/app/routes/.
PATH_ACTIVE_ELECTIONS = "/elections/active"
PATH_ELECTION_HISTORY = "/elections/history"
PATH_VOTE_HISTORY = "/votes/history"
PATH_PROFILE = "/users/me"
PATH_VOTES = "/votes/"

# The exact 400 detail the vote route returns for a second ballot
# (backend/app/routes/vote_routes.py). Recorded as a failure, never as success.
DUPLICATE_VOTE_DETAIL = "You have already voted in this election"


class PoolExhausted(PerfError):
    """Every prepared voter has already been claimed by another virtual user."""


class VoteBudgetExceeded(PerfError):
    """A second vote was attempted for a voter that has already tried once."""


# ── Errors and target safety ──────────────────────────────────────────────────


def resolve_scenario(env: Mapping[str, str]) -> str:
    """``PERF_SCENARIO`` must be exactly ``read`` or ``vote``.

    Matched exactly — not stripped, not lowercased — like ``PERF_SETUP_ALLOWED``
    and ``PERF_VOTE_LOAD_ALLOWED``. A scenario chosen by accident is the
    difference between reading data and permanently consuming ballots, so a stray
    ``"vote "`` from a shell or an env file fails rather than arming the run.
    """
    raw = env.get(ENV_SCENARIO)

    if raw is None or raw == "":
        raise ConfigError(
            f"{ENV_SCENARIO} must be set to one of {list(VALID_SCENARIOS)}. "
            f"There is no default — the scenario is always chosen explicitly."
        )

    if raw not in VALID_SCENARIOS:
        raise ConfigError(
            f"{ENV_SCENARIO} must be exactly one of {list(VALID_SCENARIOS)}; "
            f"got {raw!r} (matched exactly — check for stray whitespace or case)"
        )

    return raw


def require_host_matches(host: str | None, staging_url: str) -> None:
    """Locust's ``--host`` must not become a way around the target guards.

    Locust takes its own ``--host`` (or ``LOCUST_HOST``), which would otherwise
    silently win over ``PERF_BASE_URL`` and point the whole run somewhere that was
    never validated. It has to match the validated target exactly, after
    normalisation.
    """
    if not (host or "").strip():
        raise SafetyError(
            "Locust was given an empty --host. Set it to PERF_BASE_URL, or omit "
            "it and let the locustfile supply the validated target."
        )

    # Raises SafetyError of its own for a malformed URL or a bad port.
    normalized = common.normalize_base_url(host)

    if normalized != staging_url:
        raise SafetyError(
            f"Locust --host ({normalized}) does not match the validated "
            f"{common.ENV_BASE_URL} ({staging_url}). Refusing to run against a "
            f"target that did not pass the safety checks."
        )


def check_user_count(users: int) -> int:
    """At most one virtual user per prepared voter."""
    if users < 1:
        raise ConfigError(f"User count must be at least 1; got {users}")

    if users > MAX_USERS:
        raise SafetyError(
            f"Refusing to run {users} users: only {MAX_USERS} voter accounts were "
            f"prepared, and a voter must never be shared between two concurrent "
            f"users. Run at most {MAX_USERS}."
        )

    return users


def require_run_user_count(run: int, users: int) -> int:
    """The election run fixes the cohort size. A mismatch is refused.

    Election 1 takes exactly 10 voters, 2 takes 25 and 3 takes 50. Running run 1
    with ``--users 50`` would consume forty extra irreversible ballots at a
    concurrency the experiment never called for, and there is no way to undo it.
    """
    if run not in VOTE_RUN_USER_COUNTS:
        raise ConfigError(
            f"Election run must be one of {list(VOTE_RUN_USER_COUNTS)}; got {run}"
        )

    expected = VOTE_RUN_USER_COUNTS[run]
    if users != expected:
        raise SafetyError(
            f"Election run {run} must be voted by exactly {expected} users, but "
            f"Locust was started with --users {users}. Refusing: every ballot is "
            f"permanent, so the cohort size is not negotiable."
        )

    return expected


def refuse_distributed(parsed_options: Any) -> None:
    """Vote runs are single-process only.

    Each process would build its own voter pool and its own barrier, so two
    processes would allocate the same voters twice and release two independent
    half-cohorts. The result would be duplicate-vote failures and a concurrency
    level that never actually happened.
    """
    if parsed_options is None:
        return

    if getattr(parsed_options, "master", False):
        raise SafetyError(
            "Refusing to run the vote scenario as a distributed master. Each "
            "worker would hold its own voter pool and barrier, so voters would be "
            "allocated twice. Run it single-process."
        )

    if getattr(parsed_options, "worker", False):
        raise SafetyError(
            "Refusing to run the vote scenario as a distributed worker. The "
            "synchronization barrier is per-process and cannot span workers."
        )

    processes = getattr(parsed_options, "processes", None)
    # Locust uses -1 for "one process per core"; anything but a single process
    # breaks the shared pool and barrier.
    if processes not in (None, 1):
        raise SafetyError(
            f"Refusing to run the vote scenario with --processes {processes}. "
            f"The voter pool and the barrier live in one process; use a single "
            f"process."
        )


def _ready_timeout(env: Mapping[str, str]) -> float:
    """Barrier timeout, validated as a positive number of seconds."""
    raw = (env.get(ENV_VOTE_READY_TIMEOUT) or "").strip()
    if not raw:
        return DEFAULT_VOTE_READY_TIMEOUT

    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(
            f"{ENV_VOTE_READY_TIMEOUT} must be a number of seconds; got {raw!r}"
        )

    if value <= 0:
        raise ConfigError(
            f"{ENV_VOTE_READY_TIMEOUT} must be greater than zero; got {value}"
        )

    return value


def _wait_seconds(env: Mapping[str, str]) -> tuple[float, float]:
    """Read the think-time window, defaulting to a realistic 1-3 seconds."""

    def read(name: str, default: float) -> float:
        raw = (env.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            raise ConfigError(f"{name} must be a number of seconds; got {raw!r}")
        if value < 0:
            raise ConfigError(f"{name} must not be negative; got {value}")
        return value

    minimum = read(ENV_MIN_WAIT, DEFAULT_MIN_WAIT)
    maximum = read(ENV_MAX_WAIT, DEFAULT_MAX_WAIT)

    if maximum < minimum:
        raise ConfigError(
            f"{ENV_MAX_WAIT} ({maximum}) must not be less than "
            f"{ENV_MIN_WAIT} ({minimum})"
        )

    return minimum, maximum


# ── Voter allocation ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClaimedVoter:
    """One prepared voter, handed to exactly one virtual user.

    ``index`` is the voter's zero-based position in the manifest and is what makes
    candidate selection deterministic and evenly spread.
    """

    index: int
    username: str
    email: str
    external_id: str


class VoterPool:
    """Hands out each prepared voter to at most one virtual user.

    Locust spawns users from multiple greenlets (and, with ``--processes``, from
    separate worker processes — see the note in README.md), so allocation is
    guarded by a lock. Claiming is strictly sequential and never wraps around:
    once the pool is empty, ``claim`` raises rather than reissuing a voter that is
    already in use.
    """

    def __init__(self, voters: Sequence[Mapping[str, Any]], *, limit: int | None = None):
        entries = list(voters)
        if limit is not None:
            if limit < 0:
                raise ConfigError("Voter pool limit must not be negative")
            entries = entries[:limit]

        self._voters = entries
        self._lock = threading.Lock()
        self._next = 0
        self._claimed: list[str] = []

    def __len__(self) -> int:
        return len(self._voters)

    @property
    def remaining(self) -> int:
        with self._lock:
            return len(self._voters) - self._next

    @property
    def claimed_usernames(self) -> list[str]:
        with self._lock:
            return list(self._claimed)

    def claim(self) -> ClaimedVoter:
        with self._lock:
            if self._next >= len(self._voters):
                raise PoolExhausted(
                    f"All {len(self._voters)} prepared voters are already in use. "
                    f"Reduce the user count; a voter must not be shared."
                )

            index = self._next
            self._next += 1
            entry = self._voters[index]
            self._claimed.append(str(entry["username"]))

        return ClaimedVoter(
            index=index,
            username=str(entry["username"]),
            email=str(entry["email"]),
            external_id=str(entry["external_id"]),
        )


# ── The plan ──────────────────────────────────────────────────────────────────


@dataclass
class LoadPlan:
    """Everything a virtual user needs, resolved and validated before spawning.

    ``voter_password`` is excluded from the dataclass repr. It is the one secret
    this object carries, and a plan is exactly the kind of thing that ends up in a
    log line or a traceback.
    """

    scenario: str
    base_url: str
    batch: str
    voters: list[dict[str, Any]]
    election_ids: list[str]
    min_wait: float
    max_wait: float
    voter_password: str = field(repr=False)
    vote_election: dict[str, Any] | None = None
    vote_ready_timeout: float = DEFAULT_VOTE_READY_TIMEOUT
    pool: VoterPool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.pool = VoterPool(self.voters)

    @property
    def expected_voters(self) -> int:
        """The cohort size fixed by the selected election run."""
        if not self.vote_election:
            raise ConfigError("expected_voters is only defined for the vote scenario")
        return VOTE_RUN_USER_COUNTS[int(self.vote_election["run"])]

    def limit_users(self, users: int) -> None:
        """Cap the pool at the number of users Locust was actually asked for.

        This is what keeps a vote run to the size it was commissioned at. Locust
        replaces a virtual user that stops, and each vote user stops after its
        single ballot, so without this cap a long ``--run-time`` would keep
        spawning replacements and quietly consume all fifty voters on an election
        that was only meant to receive ten votes.
        """
        check_user_count(users)
        self.pool = VoterPool(self.voters, limit=users)

    @property
    def candidates(self) -> list[dict[str, Any]]:
        if not self.vote_election:
            return []
        return list(self.vote_election.get("candidates", []))

    def candidate_for(self, voter_index: int) -> dict[str, Any]:
        """Deterministic, evenly spread choice: voter N takes candidate N mod 2.

        Reproducible across runs, and it splits the ballots roughly evenly between
        the two candidates so a tally is a meaningful check rather than a
        landslide that could hide a counting error.
        """
        candidates = self.candidates
        if not candidates:
            raise ConfigError("No candidates are available for the vote scenario")
        return candidates[voter_index % len(candidates)]


def build_plan(
    env: Mapping[str, str] | None = None,
    *,
    host: str | None = None,
    data_dir: Any = None,
) -> LoadPlan:
    """Resolve and validate everything, or raise before a single user is spawned.

    Order matters. The scenario and the target are settled first, then the
    manifest, then the vote-specific arming. Nothing here opens a connection.
    """
    env = os.environ if env is None else env

    scenario = resolve_scenario(env)

    # Both scenarios log in as voters, so the voter password is always required.
    config = common.load_config(env, require_voter_password=True)

    # The same guards the setup and verification scripts use: HTTPS, production
    # supplied, different from staging, and named like a test target.
    staging_url = common.validate_target(
        config.base_url,
        config.production_base_url,
        local_allowed=config.local_test_allowed,
    )

    if host is not None:
        require_host_matches(host, staging_url)

    manifest_file = common.manifest_path(config.batch, data_dir)
    manifest = common.load_manifest(manifest_file)
    if manifest is None:
        raise ManifestError(
            f"No manifest at {manifest_file}. Run setup_performance_data and "
            f"verify_performance_data before load testing."
        )

    # strict=True: a half-prepared data set is not something to load test.
    common.validate_manifest(
        manifest, batch=config.batch, base_url=staging_url, strict=True
    )

    voters = [dict(voter) for voter in manifest["voters"]]
    elections = list(manifest["elections"])

    vote_election = None
    if scenario == SCENARIO_VOTE:
        vote_election = resolve_vote_election(env, elections)

    minimum, maximum = _wait_seconds(env)

    return LoadPlan(
        scenario=scenario,
        base_url=staging_url,
        batch=config.batch,
        voters=voters,
        election_ids=[str(entry["election_id"]) for entry in elections],
        min_wait=minimum,
        max_wait=maximum,
        voter_password=config.voter_password or "",
        vote_election=vote_election,
        vote_ready_timeout=_ready_timeout(env),
    )


def resolve_vote_election(
    env: Mapping[str, str], elections: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Arm the vote scenario, or refuse.

    Voting is off unless it is switched on deliberately and pointed at one named
    election. Every ballot it casts is irreversible — there is no unvote endpoint
    — so nothing here is inferred or defaulted.
    """
    allowed = env.get(ENV_VOTE_LOAD_ALLOWED)
    if allowed != "true":
        raise SafetyError(
            f"Vote load is disabled. Set {ENV_VOTE_LOAD_ALLOWED}=true (exactly, "
            f"lowercase) to arm it; got {allowed!r}. Each vote permanently "
            f"consumes that voter's ballot for the selected election."
        )

    raw_run = (env.get(ENV_VOTE_ELECTION_RUN) or "").strip()
    if not raw_run:
        raise ConfigError(
            f"{ENV_VOTE_ELECTION_RUN} must be set to one of "
            f"{list(VALID_ELECTION_RUNS)}. The election is never chosen for you."
        )

    try:
        run = int(raw_run)
    except ValueError:
        raise ConfigError(
            f"{ENV_VOTE_ELECTION_RUN} must be one of {list(VALID_ELECTION_RUNS)}; "
            f"got {raw_run!r}"
        )

    if run not in VALID_ELECTION_RUNS:
        raise ConfigError(
            f"{ENV_VOTE_ELECTION_RUN} must be one of {list(VALID_ELECTION_RUNS)}; "
            f"got {run}"
        )

    entry = next((e for e in elections if e.get("run") == run), None)
    if entry is None:
        raise ConfigError(f"The manifest has no election for run {run}")

    validate_vote_election(entry)
    return dict(entry)


def validate_vote_election(entry: Mapping[str, Any]) -> None:
    """Refuse an election that is missing, not active, expired or misconfigured."""
    election_id = str(entry.get("election_id") or "").strip()
    if not election_id:
        raise ConfigError("The selected election has no election_id")

    status = entry.get("status")
    if status != "active":
        raise SafetyError(
            f"Election run {entry.get('run')} has status {status!r}, not 'active'. "
            f"Refusing to cast ballots into it."
        )

    if entry.get("ballot_type") not in (None, common.BALLOT_TYPE):
        raise SafetyError(
            f"Election run {entry.get('run')} is a "
            f"{entry.get('ballot_type')!r} ballot, expected "
            f"{common.BALLOT_TYPE!r}"
        )

    candidates = entry.get("candidates") or []
    if len(candidates) != len(common.CANDIDATE_NAMES):
        raise SafetyError(
            f"Election run {entry.get('run')} has {len(candidates)} candidates, "
            f"expected {len(common.CANDIDATE_NAMES)}"
        )

    end_date = entry.get("end_date")
    if not end_date:
        raise SafetyError(f"Election run {entry.get('run')} has no end date")

    remaining = common.parse_api_datetime(str(end_date)) - common.now_sgt()
    if remaining.total_seconds() <= 0:
        raise SafetyError(
            f"Election run {entry.get('run')} closed at {end_date}. Refusing to "
            f"vote in an expired election."
        )


def preflight_vote_election(
    plan: LoadPlan,
    *,
    transport: Any = None,
) -> dict[str, Any]:
    """Confirm against the live API that the target election is still votable.

    The manifest records the election as it was at creation time; this re-reads it
    just before the run so a completed or extended election is caught. Uses the
    read-only client from ``common``, so this check is structurally incapable of
    changing anything.

    Deliberately does *not* touch ``GET /results/elections/{id}`` — that endpoint
    is the only trigger for finalization and would tally and close an election
    whose deadline had passed.
    """
    if not plan.vote_election:
        raise ConfigError("preflight_vote_election requires the vote scenario")

    voter = plan.voters[0]
    election_id = plan.vote_election["election_id"]

    with common.build_client(
        plan.base_url, transport=transport, read_only=True
    ) as client:
        token = common.login(client, str(voter["email"]), plan.voter_password)
        response = client.get(
            f"/elections/{election_id}", headers=common.auth_headers(token)
        )

    if response.status_code != 200:
        raise SafetyError(
            f"Pre-flight failed: GET /elections/{{id}} returned "
            f"{response.status_code} for run {plan.vote_election.get('run')}"
        )

    body = response.json()
    live = {
        "run": plan.vote_election.get("run"),
        "election_id": election_id,
        "status": body.get("status"),
        "ballot_type": body.get("ballot_type"),
        "end_date": body.get("end_date"),
        "candidates": plan.vote_election.get("candidates"),
    }
    validate_vote_election(live)

    return body


# ── Virtual-user behaviour ────────────────────────────────────────────────────


class VoterSession:
    """One virtual user's conversation with the API.

    Holds the JWT in memory for the life of the user and nowhere else: it is never
    written to the manifest, to a CSV, or into a failure message. Failure strings
    are built from status codes and fixed text only.
    """

    def __init__(self, plan: LoadPlan, voter: ClaimedVoter):
        self.plan = plan
        self.voter = voter
        self._token: str | None = None
        # Set before the vote request is sent, never after — see cast_vote.
        self._vote_attempted = False

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<VoterSession {self.voter.username} authenticated={self.authenticated}>"

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    @property
    def vote_attempted(self) -> bool:
        return self._vote_attempted

    @property
    def headers(self) -> dict[str, str]:
        """Bearer header for every authenticated request (backend uses HTTPBearer)."""
        if not self._token:
            raise PerfError("Not authenticated: log in before making requests")
        return common.auth_headers(self._token)

    # ── authentication ────────────────────────────────────────────────────────

    def login(self, client: Any) -> bool:
        """Log in once and keep the token in memory. Returns success."""
        with client.post(
            common.LOGIN_PATH,
            json={"email": self.voter.email, "password": self.plan.voter_password},
            name=NAME_LOGIN,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login returned {response.status_code}")
                return False

            body = _json_or_none(response)
            if body is None:
                response.failure("login returned a malformed body")
                return False

            token = body.get("access_token")
            if not token:
                response.failure("login response carried no access_token")
                return False

            response.success()

        self._token = str(token)
        return True

    # ── read scenario ─────────────────────────────────────────────────────────

    def read_active_elections(self, client: Any) -> list[dict[str, Any]]:
        return self._read_list(client, PATH_ACTIVE_ELECTIONS, NAME_ACTIVE_ELECTIONS)

    def read_election_history(self, client: Any) -> list[dict[str, Any]]:
        return self._read_list(client, PATH_ELECTION_HISTORY, NAME_ELECTION_HISTORY)

    def read_vote_history(self, client: Any) -> list[dict[str, Any]]:
        return self._read_list(client, PATH_VOTE_HISTORY, NAME_VOTE_HISTORY)

    def read_election_detail(self, client: Any, election_id: str) -> dict[str, Any] | None:
        """One election by id, reported under a normalised name.

        The id is in the URL but never in the Locust request name, so all three
        elections aggregate into a single statistics row.
        """
        with client.get(
            f"/elections/{election_id}",
            name=NAME_ELECTION_DETAIL,
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
                return None

            body = _json_or_none(response)
            if not isinstance(body, dict) or not body.get("id"):
                response.failure("election detail was malformed")
                return None

            response.success()
            return body

    def read_vote_detail(self, client: Any, vote_id: str) -> dict[str, Any] | None:
        with client.get(
            f"/votes/{vote_id}",
            name=NAME_VOTE_DETAIL,
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
                return None

            body = _json_or_none(response)
            if not isinstance(body, dict) or not body.get("receipt_code"):
                response.failure("vote detail was malformed")
                return None

            response.success()
            return body

    def read_profile(self, client: Any) -> dict[str, Any] | None:
        with client.get(
            PATH_PROFILE,
            name=NAME_PROFILE,
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
                return None

            body = _json_or_none(response)
            if not isinstance(body, dict) or body.get("email") != self.voter.email:
                response.failure("profile did not describe the expected account")
                return None

            response.success()
            return body

    def _read_list(self, client: Any, path: str, name: str) -> list[dict[str, Any]]:
        return self._read_list_result(client, path, name)[1]

    def _read_list_result(
        self, client: Any, path: str, name: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        """As ``_read_list``, but also says whether the request itself succeeded.

        The read scenario only wants the rows and treats a failure as an empty
        list. The vote readiness check has to tell "this voter has no ballots"
        apart from "the request failed", because the first means ready and the
        second must abort the run.
        """
        with client.get(
            path, name=name, headers=self.headers, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
                return False, []

            body = _json_or_none(response)
            if not isinstance(body, list):
                response.failure("expected a JSON list")
                return False, []

            response.success()
            return True, body

    # ── vote scenario ─────────────────────────────────────────────────────────

    def check_vote_readiness(self, client: Any) -> str | None:
        """Confirm this voter can cast a valid ballot. Returns None when ready.

        Two authenticated, read-only requests, both of which the voter is allowed
        to make on its own behalf — no organizer session is needed inside the load
        test:

        ``GET /elections/{id}``
            A 200 proves two things at once. The election exists (404 otherwise),
            and *this voter is eligible for it* — the route answers 403 to a voter
            with no ElectionVoter row (backend/app/routes/election_routes.py).
            The body then supplies status, start/end dates, ballot configuration
            and candidates to check against the manifest.

        ``GET /votes/history``
            The voter's own ballots. An entry for the selected election means this
            voter has already voted in it, so the run must not proceed.

        ``GET /results/elections/{id}`` is never called: it is the only trigger
        for finalization and would tally and close the election.
        """
        election = self.plan.vote_election
        if not election:
            raise ConfigError("check_vote_readiness requires the vote scenario")

        election_id = str(election["election_id"])

        with client.get(
            f"/elections/{election_id}",
            name=NAME_ELECTION_DETAIL,
            headers=self.headers,
            catch_response=True,
        ) as response:
            status = response.status_code

            if status == 403:
                response.failure("voter is not eligible for the selected election")
                return "not eligible for the selected election"

            if status == 404:
                response.failure("selected election not found")
                return "selected election not found"

            if status != 200:
                response.failure(f"unexpected status {status}")
                return f"election read returned {status}"

            body = _json_or_none(response)
            if not isinstance(body, dict):
                response.failure("election detail was malformed")
                return "election detail was malformed"

            response.success()

        mismatch = describe_election_mismatch(body, election)
        if mismatch:
            return mismatch

        ok, history = self._read_list_result(
            client, PATH_VOTE_HISTORY, NAME_VOTE_HISTORY
        )
        if not ok:
            return "vote history could not be read"

        for entry in history:
            if str(entry.get("election_id")) == election_id:
                return "voter has already voted in the selected election"

        return None

    def cast_vote(self, client: Any) -> bool:
        """Submit this voter's single ballot. Returns whether it was accepted.

        Exactly one attempt per session, ever. The attempted flag is set *before*
        the request is sent, so an exception, a timeout or any other uncertain
        outcome cannot be retried: the server may already have recorded the
        ballot, and a retry would either double-count or produce a misleading
        duplicate-vote failure.
        """
        if self._vote_attempted:
            raise VoteBudgetExceeded(
                f"{self.voter.username} has already attempted its vote. A ballot is "
                f"never retried — the first attempt may have been accepted."
            )

        election = self.plan.vote_election
        if not election:
            raise ConfigError("cast_vote requires the vote scenario")

        candidate = self.plan.candidate_for(self.voter.index)

        # Set before sending. Every exit path below leaves it True.
        self._vote_attempted = True

        payload = {
            "election_id": str(election["election_id"]),
            "candidate_id": str(candidate["id"]),
        }

        with client.post(
            PATH_VOTES,
            json=payload,
            name=NAME_CAST_VOTE,
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                body = _json_or_none(response)
                if not isinstance(body, dict) or not body.get("receipt_code"):
                    response.failure("vote accepted but the receipt was malformed")
                    return False
                response.success()
                return True

            detail = _detail_or_none(response)

            if response.status_code == 400 and detail == DUPLICATE_VOTE_DETAIL:
                # A real defect in the run, not a success: this voter was already
                # used for this election, so the measurement is not what it claims.
                response.failure(
                    "duplicate vote — this voter had already voted in this election"
                )
                return False

            response.failure(
                f"vote rejected with {response.status_code}"
                + (f": {detail}" if detail else "")
            )
            return False


def describe_election_mismatch(
    body: Mapping[str, Any], expected: Mapping[str, Any]
) -> str | None:
    """Compare a live election against the manifest. None means it is votable.

    Checks exactly what has to hold for a ballot to be accepted by the vote
    route: active, inside its voting window, single-choice with one selection,
    and carrying the same two candidate ids the manifest recorded. Sending a vote
    to an election that fails any of these would be rejected by the backend, so
    catching it here is what keeps the run all-or-nothing.
    """
    if str(body.get("id")) != str(expected["election_id"]):
        return "election id does not match the manifest"

    if body.get("status") != "active":
        return f"election status is {body.get('status')!r}, not 'active'"

    now = common.now_sgt()

    start_date = body.get("start_date")
    if not start_date:
        return "election has no start date"
    if common.parse_api_datetime(str(start_date)) > now:
        return f"election has not started yet (starts {start_date})"

    end_date = body.get("end_date")
    if not end_date:
        return "election has no end date"
    if common.parse_api_datetime(str(end_date)) <= now:
        return f"election has expired (ended {end_date})"

    if body.get("ballot_type") != common.BALLOT_TYPE:
        return f"ballot_type is {body.get('ballot_type')!r}"

    if body.get("max_selections") != common.MAX_SELECTIONS:
        return f"max_selections is {body.get('max_selections')!r}"

    live_candidates = {
        str(candidate.get("id")): str(candidate.get("name"))
        for candidate in body.get("candidates") or []
    }
    expected_candidates = {
        str(candidate.get("id")): str(candidate.get("name"))
        for candidate in expected.get("candidates") or []
    }

    if live_candidates != expected_candidates:
        return (
            f"candidates do not match the manifest "
            f"(live {len(live_candidates)}, manifest {len(expected_candidates)})"
        )

    return None


def prepare_and_vote(
    session: "VoterSession",
    client: Any,
    coordinator: Any,
) -> str:
    """One virtual user's whole synchronized lifecycle.

    Claim, authenticate, check readiness, hold at the barrier, and — only if the
    entire cohort made it — cast exactly one ballot. Every failure path aborts the
    coordinator, which wakes the other waiters and prevents any of them voting.

    Returns one of ``aborted``, ``accepted`` or ``rejected``, for the caller's
    logging. The counters that matter live on the coordinator.
    """
    username = session.voter.username

    coordinator.claim(username)

    if not session.login(client):
        coordinator.abort("login failed", username)
        return "aborted"

    problem = session.check_vote_readiness(client)
    if problem:
        coordinator.abort(problem, username)
        return "aborted"

    if not coordinator.mark_ready(username):
        return "aborted"

    # Blocks until every expected voter is ready, or the run is abandoned.
    if not coordinator.wait_for_release():
        return "aborted"

    coordinator.record_attempt()

    try:
        accepted = session.cast_vote(client)
    except BaseException:
        # An exception leaves the ballot's fate unknown. It is counted as failed
        # and never retried — cast_vote set its attempted flag before sending.
        coordinator.record_rejected("vote raised an exception")
        raise

    if accepted:
        coordinator.record_accepted()
        return "accepted"

    coordinator.record_rejected()
    return "rejected"


def _json_or_none(response: Any) -> Any:
    """Decode a JSON body, treating any decoding problem as a malformed response."""
    try:
        return response.json()
    except Exception:  # requests raises its own JSONDecodeError subclass
        return None


def _detail_or_none(response: Any) -> str | None:
    body = _json_or_none(response)
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return None


def describe_plan(plan: LoadPlan, users: int | None = None) -> str:
    """Operator-facing summary printed at start-up. Contains no secrets."""
    lines = [
        "",
        "  Locust load test",
        "  " + "-" * 52,
        f"  Target URL   : {plan.base_url}",
        f"  Scenario     : {plan.scenario}",
        f"  Batch        : {plan.batch}",
        f"  Voter pool   : {len(plan.pool)} of {len(plan.voters)} prepared voters",
    ]

    if users is not None:
        lines.append(f"  Users        : {users}")

    if plan.vote_election:
        lines.extend(
            [
                f"  Election run : {plan.vote_election.get('run')}",
                f"  Election id  : {plan.vote_election.get('election_id')}",
                f"  Title        : {plan.vote_election.get('title')}",
                "  " + "-" * 52,
                "  VOTING IS ARMED. Each ballot is permanent and cannot be undone.",
            ]
        )
    else:
        lines.extend(
            [
                "  " + "-" * 52,
                "  Read-only scenario. No ballots are cast.",
            ]
        )

    lines.append("")
    return "\n".join(lines)
