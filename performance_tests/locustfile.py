"""Locust bindings for the prepared performance data set.

    locust -f performance_tests/locustfile.py ...

All of the logic — scenario resolution, target safety, voter allocation, request
behaviour — lives in ``load_plan.py`` and is unit-tested without Locust
installed. This file is the adapter: it resolves the plan before any user is
spawned, then defines the one user class the chosen scenario needs.

Exactly one ``HttpUser`` subclass is defined per process, chosen by
``PERF_SCENARIO``. Defining both and relying on weights would leave the wrong
scenario one typo away from spawning, and a vote user spawned by accident casts
irreversible ballots.

See README.md for the commands.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Locust loads this file by path, so the repository root is not necessarily on
# sys.path. Without this, `from performance_tests import ...` fails at import.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from locust import HttpUser, between, constant, events, task  # noqa: E402
from locust.exception import StopUser  # noqa: E402

from performance_tests import load_plan as lp  # noqa: E402
from performance_tests.common import PerfError  # noqa: E402
from performance_tests.vote_coordinator import VoteCoordinator  # noqa: E402

# Built in the init hook once the cohort size is known. Vote scenario only.
COORDINATOR: VoteCoordinator | None = None


def _fail(message: str) -> None:
    """Refuse to start. Printed to stderr, then the process exits non-zero."""
    print(f"\nERROR: {message}\n", file=sys.stderr)
    raise SystemExit(1)


# Resolved at import, which is the earliest point at which Locust can be stopped
# and is before any user class exists. --host is not known yet, so it is checked
# again in the init hook below.
try:
    PLAN = lp.build_plan(os.environ)
except PerfError as exc:
    _fail(str(exc))


@events.init.add_listener
def _validate_runtime_target(environment, **_kwargs):
    """Re-check the target once Locust's own options are parsed.

    ``--host`` (or ``LOCUST_HOST``) would otherwise override the validated
    ``PERF_BASE_URL`` and send the whole run somewhere that passed no safety
    check at all. Runs before users spawn.
    """
    global COORDINATOR

    parsed = getattr(environment, "parsed_options", None)
    host = environment.host or getattr(parsed, "host", None)
    users = getattr(parsed, "num_users", None)

    try:
        if host:
            lp.require_host_matches(host, PLAN.base_url)
        else:
            # Nothing supplied: pin Locust to the validated target.
            environment.host = PLAN.base_url

        if PLAN.scenario == lp.SCENARIO_VOTE:
            # One process only: the voter pool and the barrier are per-process.
            lp.refuse_distributed(parsed)

            if not users:
                _fail(
                    "The vote scenario needs an explicit --users matching the "
                    "election run's commissioned cohort size."
                )

            # Election run 1 -> 10 users, 2 -> 25, 3 -> 50. A mismatch stops here.
            expected = lp.require_run_user_count(
                int(PLAN.vote_election["run"]), int(users)
            )
            PLAN.limit_users(expected)
            COORDINATOR = VoteCoordinator(
                expected, timeout_seconds=PLAN.vote_ready_timeout
            )
        elif users:
            # Read scenario: unchanged.
            PLAN.limit_users(lp.check_user_count(int(users)))
    except PerfError as exc:
        _fail(str(exc))

    print(lp.describe_plan(PLAN, users=users))

    if COORDINATOR is not None:
        print(
            f"  Synchronized barrier: all {COORDINATOR.expected} voters prepare "
            f"first, then vote together.\n"
            f"  Readiness timeout: {COORDINATOR.timeout_seconds:g}s\n"
        )


@events.test_start.add_listener
def _preflight(environment, **_kwargs):
    """For the vote scenario only: confirm the election is still votable."""
    if PLAN.scenario != lp.SCENARIO_VOTE:
        return

    try:
        lp.preflight_vote_election(PLAN)
    except PerfError as exc:
        print(f"\nERROR: pre-flight refused the run: {exc}\n", file=sys.stderr)
        if environment.runner is not None:
            environment.runner.quit()
        raise SystemExit(1)


@events.test_stop.add_listener
def _print_summary(environment, **_kwargs):
    """Non-secret tallies at the end of a vote run."""
    if COORDINATOR is not None:
        print(COORDINATOR.summary().render())


class _VoterUser(HttpUser):
    """Shared start-up: claim a unique voter, log in once, keep the JWT in memory."""

    abstract = True

    def claim_voter(self):
        try:
            return PLAN.pool.claim()
        except lp.PoolExhausted:
            # Every prepared voter is in use. Stop this user rather than share one.
            raise StopUser()


if PLAN.scenario == lp.SCENARIO_READ:

    class VoterReadUser(_VoterUser):
        """Authenticated read traffic from an eligible voter.

        Deliberately never calls ``GET /results/elections/{id}``: that endpoint is
        the only trigger for finalization and would tally and close an election
        whose deadline had passed, which is a mutation, not a read.
        """

        wait_time = between(PLAN.min_wait, PLAN.max_wait)

        def on_start(self) -> None:
            self.session = lp.VoterSession(PLAN, self.claim_voter())
            if not self.session.login(self.client):
                # The failure is already recorded against POST /auth/login.
                raise StopUser()

        @task(4)
        def active_elections(self) -> None:
            self.session.read_active_elections(self.client)

        @task(3)
        def election_detail(self) -> None:
            # Rotates over the prepared elections; reported under one name.
            election_id = PLAN.election_ids[
                self.session.voter.index % len(PLAN.election_ids)
            ]
            self.session.read_election_detail(self.client, election_id)

        @task(2)
        def vote_history(self) -> None:
            history = self.session.read_vote_history(self.client)
            # Only reachable once this voter has a ballot, so it exercises the
            # detail route after a vote run without failing before one.
            if history:
                self.session.read_vote_detail(self.client, str(history[0]["id"]))

        @task(1)
        def election_history(self) -> None:
            self.session.read_election_history(self.client)

        @task(1)
        def profile(self) -> None:
            self.session.read_profile(self.client)

else:

    class VoterVoteUser(_VoterUser):
        """One voter: prepare, hold at the barrier, vote with everyone else, stop.

        Preparation (login + readiness reads) happens as the user spawns, so it is
        spread out and does not compete with the ballots. The vote itself is what
        the barrier synchronises: nobody votes until the whole cohort is ready, so
        the measurement is concurrent POST /votes/ processing rather than staggered
        authentication.

        Any preparation failure aborts the entire run before a single ballot is
        spent. A ballot is never retried.
        """

        wait_time = constant(0)

        @task
        def prepare_hold_and_vote(self) -> None:
            session = lp.VoterSession(PLAN, self.claim_voter())

            try:
                outcome = lp.prepare_and_vote(session, self.client, COORDINATOR)
                if outcome == "aborted":
                    print(
                        f"{session.voter.username}: run aborted before voting",
                        file=sys.stderr,
                    )
            except PerfError as exc:
                # Our own refusals (duplicate claim, already attempted,
                # misconfiguration). Reported once, never retried.
                print(f"vote aborted for this user: {exc}", file=sys.stderr)

            # Stops whatever the outcome, so a ballot can never be attempted twice.
            raise StopUser()
