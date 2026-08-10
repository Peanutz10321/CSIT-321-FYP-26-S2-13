"""Read-only readiness check for the performance-test data.

Run it with ``python -m performance_tests.verify_performance_data`` from the
repository root. It creates, updates and deletes nothing: the client it builds is
constructed with ``read_only=True``, which installs an httpx request hook that
raises before any PUT, PATCH, DELETE or non-login POST leaves the process.

``POST /auth/login`` is the one permitted non-GET call. Verification has to
authenticate as the organizer to read the eligibility list at all, and the login
route creates no records — it reads one user row and returns a token.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import httpx

from performance_tests import common, load_plan as lp
from performance_tests.common import ConfigError, PerfConfig, PerfError


Writer = Callable[[str], None]


def _default_writer(message: str) -> None:
    print(message, flush=True)


class Report:
    """Collects pass/fail lines so every check runs before the summary is printed.

    A verification run that stopped at the first problem would need as many
    reruns as there are problems; collecting them means one run tells the whole
    story. ``ok`` is what drives the exit status.
    """

    def __init__(self) -> None:
        self.checks: list[tuple[bool, str]] = []

    def record(self, passed: bool, message: str) -> bool:
        self.checks.append((passed, message))
        return passed

    def require(self, passed: bool, message: str) -> bool:
        return self.record(passed, message)

    @property
    def failures(self) -> list[str]:
        return [message for passed, message in self.checks if not passed]

    @property
    def ok(self) -> bool:
        return not self.failures

    def render(self) -> str:
        lines = [""]
        for passed, message in self.checks:
            lines.append(f"  [{'PASS' if passed else 'FAIL'}] {message}")
        lines.append("")
        if self.ok:
            lines.append(f"  READY — {len(self.checks)} checks passed.")
        else:
            lines.append(
                f"  NOT READY — {len(self.failures)} of {len(self.checks)} "
                f"checks failed."
            )
        lines.append("")
        return "\n".join(lines)


# ── Individual checks ─────────────────────────────────────────────────────────


def check_voters(manifest: Mapping[str, Any], report: Report) -> list[str]:
    """Exactly fifty voters, each unique on username, email and external id."""
    voters = manifest.get("voters", [])

    report.require(
        len(voters) == common.VOTER_COUNT,
        f"Manifest holds {len(voters)} voters (expected {common.VOTER_COUNT})",
    )

    usernames = {v.get("username") for v in voters}
    emails = {v.get("email") for v in voters}
    external_ids = [str(v.get("external_id")) for v in voters]

    report.require(
        len(usernames) == len(voters),
        f"Voter usernames are unique ({len(usernames)} distinct)",
    )
    report.require(
        len(emails) == len(voters),
        f"Voter emails are unique ({len(emails)} distinct)",
    )
    report.require(
        len(set(external_ids)) == len(voters),
        f"Voter external ids are unique ({len(set(external_ids))} distinct)",
    )

    return external_ids


def check_election(
    client: httpx.Client,
    entry: Mapping[str, Any],
    *,
    config: PerfConfig,
    expected_external_ids: Sequence[str],
    token: str,
    report: Report,
) -> None:
    """Fetch one election and its eligible voters, and check every requirement."""
    run = entry.get("run")
    election_id = entry.get("election_id")
    label = f"Election run {run} ({election_id})"
    headers = common.auth_headers(token)

    response = client.get(f"/elections/{election_id}", headers=headers)
    if not report.require(
        response.status_code == 200,
        f"{label}: readable by the organizer "
        f"(GET /elections/{{id}} -> {response.status_code})",
    ):
        return

    body = response.json()

    expected_title = common.election_title(config.batch, run)
    report.require(
        body.get("title") == expected_title,
        f"{label}: title is {expected_title!r} (got {body.get('title')!r})",
    )
    report.require(
        body.get("status") == "active",
        f"{label}: status is active (got {body.get('status')!r})",
    )
    report.require(
        body.get("ballot_type") == common.BALLOT_TYPE,
        f"{label}: single-choice ballot (got {body.get('ballot_type')!r})",
    )
    report.require(
        body.get("max_selections") == common.MAX_SELECTIONS,
        f"{label}: max_selections == 1 (got {body.get('max_selections')!r})",
    )

    candidates = body.get("candidates") or []
    names = sorted(str(c.get("name")) for c in candidates)
    report.require(
        names == sorted(common.CANDIDATE_NAMES),
        f"{label}: has exactly the two expected candidates (got {names!r})",
    )

    designated = str(entry.get("candidate_id"))
    report.require(
        designated in {str(c.get("id")) for c in candidates},
        f"{label}: the designated candidate_id is one of its candidates",
    )

    end_date = body.get("end_date")
    if end_date:
        remaining = common.parse_api_datetime(str(end_date)) - common.now_sgt()
        report.require(
            remaining.total_seconds() > 0,
            f"{label}: end time is in the future "
            f"({remaining.total_seconds() / 3600:.1f}h remaining)",
        )
    else:
        report.require(False, f"{label}: has an end date")

    check_eligible_voters(
        client,
        election_id,
        label=label,
        expected_external_ids=expected_external_ids,
        token=token,
        report=report,
    )


def check_eligible_voters(
    client: httpx.Client,
    election_id: Any,
    *,
    label: str,
    expected_external_ids: Sequence[str],
    token: str,
    report: Report,
) -> None:
    """The eligibility list must be exactly the manifest's fifty, none of whom voted."""
    response = client.get(
        f"/elections/{election_id}/voters", headers=common.auth_headers(token)
    )
    if not report.require(
        response.status_code == 200,
        f"{label}: eligible voters readable "
        f"(GET /elections/{{id}}/voters -> {response.status_code})",
    ):
        return

    rows = response.json() or []
    found = {str(row.get("voter_external_id")) for row in rows}
    expected = set(expected_external_ids)

    missing = expected - found
    unexpected = found - expected

    report.require(
        len(rows) == len(expected),
        f"{label}: has {len(expected)} eligible voters (got {len(rows)})",
    )
    report.require(
        not missing,
        f"{label}: every manifest voter is eligible"
        + (f" (missing {len(missing)}: {sorted(missing)[:3]}…)" if missing else ""),
    )
    report.require(
        not unexpected,
        f"{label}: no unexpected eligible voters"
        + (
            f" (found {len(unexpected)}: {sorted(unexpected)[:3]}…)"
            if unexpected
            else ""
        ),
    )

    voted = [
        str(row.get("voter_external_id"))
        for row in rows
        if row.get("voted_at") is not None
    ]
    report.require(
        not voted,
        f"{label}: unused — no voter has voted"
        + (f" ({len(voted)} already voted: {sorted(voted)[:3]}…)" if voted else ""),
    )


def check_voter_logins(
    client: httpx.Client,
    manifest: Mapping[str, Any],
    password: str,
    *,
    report: Report,
    write: Writer,
) -> None:
    """``--check-logins``: authenticate as all fifty voters.

    Off by default because it is fifty extra requests and fifty bcrypt
    verifications against a staging deployment, which is exactly the load the
    real test is supposed to measure.
    """
    failures: list[str] = []

    for index, voter in enumerate(manifest.get("voters", []), start=1):
        try:
            common.login(client, str(voter["email"]), password)
        except PerfError as exc:
            failures.append(f"{voter.get('username')}: {exc}")
        write(f"Checked login {index:03d}/{common.VOTER_COUNT:03d}")

    report.require(
        not failures,
        f"All {common.VOTER_COUNT} voter logins succeed"
        + (f" ({len(failures)} failed: {failures[:3]})" if failures else ""),
    )


# ── Orchestration ─────────────────────────────────────────────────────────────


def run_verification(
    config: PerfConfig,
    *,
    check_logins: bool = False,
    transport: httpx.BaseTransport | None = None,
    data_dir: Path | None = None,
    write: Writer = _default_writer,
) -> Report:
    """Validate the manifest and confirm the live data matches it.

    The same target guards the setup script uses are applied first, so a
    verification run cannot be pointed at production either. ``PERF_SETUP_ALLOWED``
    is deliberately *not* required: this run changes nothing.
    """
    staging_url = common.validate_target(
        config.base_url,
        config.production_base_url,
        local_allowed=config.local_test_allowed,
    )

    manifest_file = common.manifest_path(config.batch, data_dir)
    report = Report()

    write(f"Verifying batch {config.batch} against {staging_url}")
    write(f"Manifest: {manifest_file}")

    manifest = common.load_manifest(manifest_file)
    if manifest is None:
        report.require(False, f"Manifest {manifest_file} exists")
        return report

    try:
        common.validate_manifest(
            manifest, batch=config.batch, base_url=staging_url, strict=True
        )
        report.require(True, "Manifest schema and batch/base-url match")
    except PerfError as exc:
        report.require(False, f"Manifest is valid: {exc}")
        return report

    external_ids = check_voters(manifest, report)

    elections = manifest.get("elections", [])
    report.require(
        len(elections) == common.ELECTION_COUNT,
        f"Manifest holds {len(elections)} elections "
        f"(expected {common.ELECTION_COUNT})",
    )

    with common.build_client(
        staging_url, transport=transport, read_only=True
    ) as client:
        try:
            common.check_health(client)
            report.require(True, "GET /health/db reports the database connected")
        except PerfError as exc:
            report.require(False, f"Health check: {exc}")
            return report

        try:
            token = common.login(
                client, config.organizer_email, config.organizer_password
            )
            report.require(True, f"Organizer {config.organizer_email} can log in")
        except PerfError as exc:
            report.require(False, f"Organizer login: {exc}")
            return report

        for entry in elections:
            check_election(
                client,
                entry,
                config=config,
                expected_external_ids=external_ids,
                token=token,
                report=report,
            )

        if check_logins:
            if not config.voter_password:
                report.require(
                    False,
                    f"--check-logins requires {common.ENV_VOTER_PASSWORD} to be set",
                )
            else:
                check_voter_logins(
                    client, manifest, config.voter_password, report=report, write=write
                )

    return report


# ── Selected-election readiness (--vote-run-ready) ────────────────────────────


def run_vote_run_verification(
    config: PerfConfig,
    run: int,
    *,
    transport: httpx.BaseTransport | None = None,
    data_dir: Path | None = None,
    write: Writer = _default_writer,
) -> Report:
    """Read-only readiness check for ONE election run's vote test.

    The full ``READY`` check covers all three elections and every voter, so it
    correctly reports NOT READY the moment run 1 has been voted in — even though
    runs 2 and 3 are still pristine and perfectly testable. This narrower mode
    answers only "can I run the vote test on run N right now", so a consumed run 1
    does not block run 2.

    It checks strictly less than the full mode and never replaces it: run the full
    verifier once after setup, then this one before each vote test.
    """
    staging_url = common.validate_target(
        config.base_url,
        config.production_base_url,
        local_allowed=config.local_test_allowed,
    )

    if run not in lp.VALID_ELECTION_RUNS:
        raise ConfigError(
            f"--vote-run-ready must be one of {list(lp.VALID_ELECTION_RUNS)}; "
            f"got {run}"
        )

    manifest_file = common.manifest_path(config.batch, data_dir)
    report = Report()

    expected_users = lp.VOTE_RUN_USER_COUNTS[run]
    write(f"Checking vote readiness for election run {run} against {staging_url}")
    write(f"Manifest: {manifest_file}")
    write(f"This run is voted by exactly {expected_users} users.")

    manifest = common.load_manifest(manifest_file)
    if manifest is None:
        report.require(False, f"Manifest {manifest_file} exists")
        return report

    try:
        common.validate_manifest(
            manifest, batch=config.batch, base_url=staging_url, strict=True
        )
        report.require(True, "Manifest schema and batch/base-url match")
    except PerfError as exc:
        report.require(False, f"Manifest is valid: {exc}")
        return report

    entry = next(
        (e for e in manifest.get("elections", []) if e.get("run") == run), None
    )
    if entry is None:
        report.require(False, f"Manifest holds an election for run {run}")
        return report

    external_ids = [str(v["external_id"]) for v in manifest.get("voters", [])]
    report.require(
        len(set(external_ids)) == common.VOTER_COUNT,
        f"Manifest holds {common.VOTER_COUNT} unique voters "
        f"(got {len(set(external_ids))})",
    )

    with common.build_client(
        staging_url, transport=transport, read_only=True
    ) as client:
        try:
            common.check_health(client)
            report.require(True, "GET /health/db reports the database connected")
        except PerfError as exc:
            report.require(False, f"Health check: {exc}")
            return report

        try:
            token = common.login(
                client, config.organizer_email, config.organizer_password
            )
            report.require(True, f"Organizer {config.organizer_email} can log in")
        except PerfError as exc:
            report.require(False, f"Organizer login: {exc}")
            return report

        # Deliberately only this election. Ballots cast in the other two runs are
        # expected and must not affect this answer.
        check_election(
            client,
            entry,
            config=config,
            expected_external_ids=external_ids,
            token=token,
            report=report,
        )

        # The vote route also needs the election to have started, which the
        # general check does not assert.
        response = client.get(
            f"/elections/{entry['election_id']}", headers=common.auth_headers(token)
        )
        if response.status_code == 200:
            mismatch = lp.describe_election_mismatch(response.json(), entry)
            report.require(
                mismatch is None,
                f"Election run {run} is votable right now"
                + (f" ({mismatch})" if mismatch else ""),
            )

    if report.ok:
        write("")
        write(
            f"Run {run} is ready for a synchronized {expected_users}-voter test. "
            f"This is irreversible and must be done once only."
        )

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m performance_tests.verify_performance_data",
        description=(
            "Read-only readiness check for the performance-test data. "
            "Creates, updates and deletes nothing."
        ),
    )
    parser.add_argument(
        "--check-logins",
        action="store_true",
        help=(
            "Also log in as all 50 voters to verify their credentials. "
            "Off by default — it is 50 extra requests against staging."
        ),
    )
    parser.add_argument(
        "--vote-run-ready",
        type=int,
        metavar="RUN",
        choices=list(lp.VALID_ELECTION_RUNS),
        help=(
            "Check only whether election RUN (1, 2 or 3) is ready for its vote "
            "test. Unlike the full check, ballots already cast in the other runs "
            "do not make this fail."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = common.load_config(require_voter_password=args.check_logins)

        if args.vote_run_ready is not None:
            report = run_vote_run_verification(config, args.vote_run_ready)
        else:
            report = run_verification(config, check_logins=args.check_logins)
    except PerfError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
