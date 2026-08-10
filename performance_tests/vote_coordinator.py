"""All-or-nothing synchronization barrier for the vote scenario.

The point of the vote test is to measure how the backend handles concurrent
``POST /votes/`` processing — Paillier encryption under the election row lock.
If the voters simply voted as they spawned, the measurement would be dominated
by staggered logins and bcrypt verification, which is authentication congestion,
not vote throughput.

So preparation and voting are separated. Every user logs in and passes its
readiness checks at its own pace, then *waits*. Only once every expected voter is
holding at the barrier are they all released to vote at once.

Preparation is all-or-nothing. A single failure anywhere — login, eligibility,
already-voted, a malformed response, or the readiness timeout — aborts the whole
run and releases the waiters *without* letting any of them vote. A half-prepared
run would consume some ballots irreversibly while measuring a concurrency level
that was never actually reached, which is worse than no measurement at all.

Concurrency primitives
----------------------
This module uses plain ``threading.RLock`` and ``threading.Event``. That is
deliberate and is gevent-compatible: Locust calls ``gevent.monkey.patch_all()``
at start-up, which replaces the ``threading`` primitives with greenlet-aware
equivalents, so these become cooperative rather than OS-level under Locust. The
same code runs correctly against real threads, which is what the unit tests use.
Importing gevent here would make the module unimportable without Locust
installed, for no behavioural gain.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from performance_tests.common import ConfigError, PerfError


DEFAULT_READY_TIMEOUT_SECONDS = 600.0


class CoordinatorError(PerfError):
    """The coordinator was used in a way that would invalidate the run."""


class DuplicateVoterError(CoordinatorError):
    """The same voter account was claimed twice."""


@dataclass(frozen=True)
class VoteSummary:
    """Non-secret tallies for the end-of-run report."""

    expected: int
    prepared: int
    attempts: int
    accepted: int
    failed: int
    aborted: bool
    abort_reason: str | None
    released: bool

    def render(self) -> str:
        return "\n".join(
            [
                "",
                "  Synchronized vote run",
                "  " + "-" * 40,
                f"  Expected voters: {self.expected}",
                f"  Prepared voters: {self.prepared}",
                f"  Vote attempts:   {self.attempts}",
                f"  Accepted votes:  {self.accepted}",
                f"  Failed votes:    {self.failed}",
                f"  Aborted:         {'yes' if self.aborted else 'no'}"
                + (f" ({self.abort_reason})" if self.abort_reason else ""),
                "  " + "-" * 40,
                "  Timing percentiles come from Locust's own CSV output.",
                "",
            ]
        )


class VoteCoordinator:
    """Tracks preparation and holds every voter until the whole cohort is ready.

    Every mutating method takes the lock, so the counters are consistent no
    matter how the greenlets interleave. The barrier itself is a single Event:
    it is set exactly once, either by the last voter becoming ready or by an
    abort, and both paths wake every waiter.
    """

    def __init__(self, expected: int, *, timeout_seconds: float = DEFAULT_READY_TIMEOUT_SECONDS):
        if expected < 1:
            raise ConfigError(f"Expected voter count must be at least 1; got {expected}")
        if timeout_seconds <= 0:
            raise ConfigError(
                f"Readiness timeout must be a positive number of seconds; "
                f"got {timeout_seconds}"
            )

        self.expected = int(expected)
        self.timeout_seconds = float(timeout_seconds)

        self._lock = threading.RLock()
        self._released = threading.Event()

        self._claimed: set[str] = set()
        self._ready: list[str] = []
        self._failures: list[tuple[str | None, str]] = []
        self._aborted = False
        self._abort_reason: str | None = None
        self._attempts = 0
        self._accepted = 0
        self._rejected = 0

    # ── observation ───────────────────────────────────────────────────────────

    @property
    def aborted(self) -> bool:
        with self._lock:
            return self._aborted

    @property
    def released(self) -> bool:
        return self._released.is_set()

    @property
    def ready_count(self) -> int:
        with self._lock:
            return len(self._ready)

    @property
    def prepared(self) -> list[str]:
        with self._lock:
            return list(self._ready)

    @property
    def failures(self) -> list[tuple[str | None, str]]:
        with self._lock:
            return list(self._failures)

    @property
    def attempts(self) -> int:
        with self._lock:
            return self._attempts

    @property
    def accepted(self) -> int:
        with self._lock:
            return self._accepted

    @property
    def rejected(self) -> int:
        with self._lock:
            return self._rejected

    @property
    def claimed(self) -> set[str]:
        with self._lock:
            return set(self._claimed)

    def summary(self) -> VoteSummary:
        with self._lock:
            return VoteSummary(
                expected=self.expected,
                prepared=len(self._ready),
                attempts=self._attempts,
                accepted=self._accepted,
                failed=self._rejected,
                aborted=self._aborted,
                abort_reason=self._abort_reason,
                released=self._released.is_set(),
            )

    # ── preparation ───────────────────────────────────────────────────────────

    def claim(self, username: str) -> None:
        """Register that this account has been allocated to a virtual user.

        A second claim on the same account is a hard error rather than a warning:
        two users sharing one voter means one of them would receive the
        duplicate-vote rejection and the concurrency level would be a lie. The
        voter pool already guarantees uniqueness; this is the independent check
        that it did.
        """
        with self._lock:
            if username in self._claimed:
                raise DuplicateVoterError(
                    f"{username} was claimed twice. A voter is never shared and "
                    f"never replaced."
                )
            self._claimed.add(username)

    def mark_ready(self, username: str) -> bool:
        """Record a fully prepared voter, releasing the barrier once all are in.

        Returns False if the run has already been aborted, in which case the
        caller must not vote.
        """
        with self._lock:
            if self._aborted:
                return False

            if username not in self._claimed:
                raise CoordinatorError(
                    f"{username} became ready without claiming an account first"
                )

            if username in self._ready:
                raise CoordinatorError(f"{username} was marked ready twice")

            self._ready.append(username)

            if len(self._ready) > self.expected:
                # More users than the run was commissioned for. Refuse rather than
                # let an over-sized cohort vote.
                self._do_abort(
                    username,
                    f"more voters became ready ({len(self._ready)}) than the "
                    f"expected {self.expected}",
                )
                return False

            if len(self._ready) == self.expected:
                # The last voter in. Everyone goes at once.
                self._released.set()

            return True

    def abort(self, reason: str, username: str | None = None) -> None:
        """Fail the whole run and wake every waiting voter without voting.

        Idempotent: the first reason is the one reported, and later failures are
        still recorded so the operator sees everything that went wrong.
        """
        with self._lock:
            self._do_abort(username, reason)

    def _do_abort(self, username: str | None, reason: str) -> None:
        """Caller must hold the lock."""
        self._failures.append((username, reason))
        if not self._aborted:
            self._aborted = True
            self._abort_reason = reason
        # Set last, so a waiter that wakes always observes the aborted state.
        self._released.set()

    def wait_for_release(self) -> bool:
        """Block until the cohort is complete. Returns whether voting may proceed.

        A timeout is itself an abort: some voter never became ready, so the run is
        not the synchronized measurement it claims to be, and no ballot is spent.
        """
        if not self._released.wait(self.timeout_seconds):
            self.abort(
                f"readiness timeout after {self.timeout_seconds:g}s with "
                f"{self.ready_count}/{self.expected} voters ready"
            )
            return False

        return self.may_vote()

    def may_vote(self) -> bool:
        """True only once the barrier has released and nothing has aborted."""
        with self._lock:
            return self._released.is_set() and not self._aborted

    # ── voting ────────────────────────────────────────────────────────────────

    def record_attempt(self) -> None:
        with self._lock:
            if self._aborted:
                raise CoordinatorError(
                    "A vote was attempted after the run was aborted. This should "
                    "be unreachable; no ballot may be spent on an aborted run."
                )
            self._attempts += 1

    def record_accepted(self) -> None:
        with self._lock:
            self._accepted += 1

    def record_rejected(self, reason: str | None = None) -> None:
        with self._lock:
            self._rejected += 1
            if reason:
                self._failures.append((None, reason))
