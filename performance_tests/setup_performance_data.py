"""Create the staging data a load test needs: 1 organizer, 50 voters, 3 elections.

Run it with ``python -m performance_tests.setup_performance_data`` from the
repository root. Every guard in ``common.py`` must pass before the first mutating
request is sent; see README.md for the full list and for why there is no cleanup
mode.

The script is resumable. It writes its manifest atomically after every single
successful creation, so an interrupted run is continued by rerunning it with the
same ``PERF_BATCH``: the work already recorded is skipped, and nothing is created
twice.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import httpx

from performance_tests import common
from performance_tests.common import (
    ApiError,
    ManifestError,
    PerfConfig,
    PerfError,
)


# Registration failures the backend reports as 400. Only these two mean "the
# account is already there"; every other 400 is a different problem and must not
# be swallowed as a duplicate.
DUPLICATE_EMAIL_DETAIL = "Account already exists."
DUPLICATE_USERNAME_DETAIL = "Username already exists."
DUPLICATE_DETAILS = frozenset({DUPLICATE_EMAIL_DETAIL, DUPLICATE_USERNAME_DETAIL})


Writer = Callable[[str], None]


def _default_writer(message: str) -> None:
    print(message, flush=True)


# ── Account creation ──────────────────────────────────────────────────────────


def register_account(
    client: httpx.Client,
    payload: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    """Register one account and return the validated UserResponse fields.

    Requires 201. A 400 that names a duplicate is re-raised with an explanation
    rather than treated as success: the response body of a duplicate carries no
    ``external_id``, so there is nothing to record, and guessing would put an
    unusable entry in the manifest.
    """
    response = client.post(common.REGISTER_PATH, json=dict(payload))

    if response.status_code == 201:
        body = response.json()
        return validate_user_response(body, payload, label=label)

    if response.status_code == 400:
        detail = common.short_detail(response)
        if detail in DUPLICATE_DETAILS:
            raise ApiError(
                f"{label}: the server says {detail!r}, but this account is not in "
                f"the manifest, so its external_id is unknown and cannot be "
                f"recovered through the public API. This usually means a previous "
                f"run created it and its manifest was lost. Use a new PERF_BATCH."
            )
        raise ApiError(f"{label}: registration rejected with 400 — {detail}")

    raise ApiError(
        f"{label}: unexpected {response.status_code} from "
        f"{common.REGISTER_PATH} — {common.short_detail(response)}"
    )


def validate_user_response(
    body: Any,
    payload: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    """Check the fields UserResponse promises, and that they match what we sent."""
    if not isinstance(body, Mapping):
        raise ApiError(f"{label}: registration response was not a JSON object")

    for field_name in ("id", "external_id", "username", "email", "role", "status"):
        if not str(body.get(field_name) or "").strip():
            raise ApiError(
                f"{label}: registration response is missing '{field_name}'"
            )

    if body["username"] != payload["username"] or body["email"] != payload["email"]:
        raise ApiError(
            f"{label}: the server returned username/email "
            f"{body['username']!r}/{body['email']!r}, which is not what was "
            f"requested. Refusing to record a mismatched account."
        )

    if body["role"] != payload["role"]:
        raise ApiError(
            f"{label}: account was created with role {body['role']!r}, "
            f"expected {payload['role']!r}"
        )

    # Only the three non-secret fields are kept. The password that was sent, and
    # anything else in the response, is dropped here and never reaches the manifest.
    return {
        "username": body["username"],
        "email": body["email"],
        "external_id": body["external_id"],
    }


def ensure_organizer(
    client: httpx.Client,
    config: PerfConfig,
    *,
    write: Writer,
) -> str:
    """Log in as the batch organizer, registering the account first if needed.

    Returns the access token. The token is handed back to the caller and never
    written anywhere — see the manifest guard in ``common.assert_no_secrets``.
    """
    try:
        token = common.login(client, config.organizer_email, config.organizer_password)
        write(f"Organizer {config.organizer_email} already exists — reusing it.")
        return token
    except ApiError as exc:
        if "Invalid credentials" not in str(exc):
            # An unexpected status (500, 403 for a suspended account, a proxy
            # error) must not be read as "not registered yet".
            raise

    write(f"Organizer {config.organizer_email} not found — registering.")
    register_account(
        client,
        {
            "username": config.organizer_username,
            "email": config.organizer_email,
            "password": config.organizer_password,
            "role": "organizer",
        },
        label="organizer",
    )

    token = common.login(client, config.organizer_email, config.organizer_password)
    write("Organizer registered and logged in.")
    return token


def create_voters(
    client: httpx.Client,
    config: PerfConfig,
    manifest: dict[str, Any],
    manifest_file: Path,
    *,
    write: Writer,
) -> None:
    """Create voters until the manifest holds all fifty.

    The manifest is the resume cursor: entry N is voter N (enforced by
    ``validate_manifest``), so the next voter to create is simply
    ``len(voters) + 1``. Nothing is queried from the database to work this out.
    """
    already = len(manifest["voters"])
    if already:
        write(
            f"Resuming: {already}/{common.VOTER_COUNT} voters already recorded in "
            f"{manifest_file.name}."
        )

    for index in range(already + 1, common.VOTER_COUNT + 1):
        payload = common.build_voter_payload(
            index, config.batch, config.voter_password
        )
        record = register_account(
            client, payload, label=f"voter {index:03d}"
        )

        manifest["voters"].append(record)
        # Checkpoint before the next request, so a crash costs at most the account
        # currently in flight rather than the whole run.
        common.save_manifest(manifest, manifest_file)

        write(f"Created voter {index:03d}/{common.VOTER_COUNT:03d}")


# ── Elections ─────────────────────────────────────────────────────────────────


def summarize_election(body: Mapping[str, Any], run: int) -> dict[str, Any]:
    """Turn an ElectionResponse into the manifest entry for one run."""
    candidates = [
        {"id": str(candidate["id"]), "name": candidate["name"]}
        for candidate in sorted(
            body.get("candidates", []),
            key=lambda c: (c.get("display_order") or 0, c.get("name") or ""),
        )
    ]

    names = [candidate["name"] for candidate in candidates]
    if names != list(common.CANDIDATE_NAMES):
        raise ApiError(
            f"Election run {run} came back with candidates {names!r}, expected "
            f"{list(common.CANDIDATE_NAMES)!r}"
        )

    return {
        "run": run,
        "election_id": str(body["id"]),
        "title": body["title"],
        "status": body["status"],
        "ballot_type": body["ballot_type"],
        "max_selections": body["max_selections"],
        "start_date": body["start_date"],
        "end_date": body["end_date"],
        # The candidate a load test should send. Pinned to the first candidate so
        # every run drives the same option and results stay comparable.
        "candidate_id": candidates[0]["id"],
        "candidates": candidates,
    }


def verify_existing_election(
    client: httpx.Client,
    entry: Mapping[str, Any],
    *,
    config: PerfConfig,
    external_ids: Sequence[str],
    token: str,
    write: Writer,
) -> None:
    """Confirm a manifest election really exists as described, or stop.

    Recreating would leave two elections with the same title and no way to tell
    which one the load test should use, so anything that does not match exactly is
    a hard stop rather than a reason to create more data.
    """
    run = entry["run"]
    headers = common.auth_headers(token)
    election_id = entry["election_id"]

    response = client.get(f"/elections/{election_id}", headers=headers)
    if response.status_code != 200:
        raise ManifestError(
            f"Election run {run} ({election_id}) is in the manifest but "
            f"GET /elections/{{id}} returned {response.status_code}. Refusing to "
            f"create a replacement — investigate first."
        )

    body = response.json()
    problems: list[str] = []

    if body.get("title") != common.election_title(config.batch, run):
        problems.append(f"title is {body.get('title')!r}")
    if body.get("status") != "active":
        problems.append(f"status is {body.get('status')!r}")
    if body.get("ballot_type") != common.BALLOT_TYPE:
        problems.append(f"ballot_type is {body.get('ballot_type')!r}")
    if body.get("max_selections") != common.MAX_SELECTIONS:
        problems.append(f"max_selections is {body.get('max_selections')!r}")
    if body.get("organizer_username") not in (None, config.organizer_username):
        problems.append(f"organizer is {body.get('organizer_username')!r}")

    names = sorted(str(c.get("name")) for c in body.get("candidates", []))
    if names != sorted(common.CANDIDATE_NAMES):
        problems.append(f"candidates are {names!r}")

    voters_response = client.get(f"/elections/{election_id}/voters", headers=headers)
    if voters_response.status_code != 200:
        problems.append(
            f"eligible voters could not be read ({voters_response.status_code})"
        )
    else:
        found = {str(row.get("voter_external_id")) for row in voters_response.json()}
        expected = set(external_ids)
        if found != expected:
            problems.append(
                f"eligible voters differ (found {len(found)}, expected "
                f"{len(expected)})"
            )

    if problems:
        raise ManifestError(
            f"Election run {run} ({election_id}) does not match what the manifest "
            f"claims: " + "; ".join(problems) + ". Stopping rather than creating "
            f"ambiguous duplicate data."
        )

    write(f"Election run {run} already exists and matches — skipping.")


def find_committed_election(
    client: httpx.Client,
    config: PerfConfig,
    run: int,
    *,
    token: str,
) -> dict[str, Any] | None:
    """Look for an election this batch already committed under run's exact title.

    This exists because ``POST /elections/`` is slow enough to time out the client
    while the server goes on to commit successfully. The election is then real but
    absent from the manifest, and a plain rerun would create a second one with the
    same title — two indistinguishable elections, and no way to know which the
    load test should use.

    Uses the organizer's own ``GET /elections/active``, whose ``search`` parameter
    is a server-side ``ILIKE %…%``. That is a *substring, case-insensitive* filter,
    so it is only a way to narrow the list: the match that decides anything is the
    exact ``==`` on the title below. ``PERF-B-RUN-01`` must never recover
    ``PERF-B-RUN-010`` or a differently-cased near-miss.

    Ownership needs no check here — for an organizer the endpoint already filters
    to ``Election.organizer_id == current_user.id``.

    Returns the single exact match, or None. Raises if there is more than one.
    """
    title = common.election_title(config.batch, run)

    response = client.get(
        common.ACTIVE_ELECTIONS_PATH,
        params={"search": title},
        headers=common.auth_headers(token),
    )

    if response.status_code != 200:
        raise ApiError(
            f"Election run {run}: could not check for an already-committed "
            f"election — GET {common.ACTIVE_ELECTIONS_PATH} returned "
            f"{response.status_code} ({common.short_detail(response)})"
        )

    body = response.json()
    if not isinstance(body, list):
        raise ApiError(
            f"Election run {run}: {common.ACTIVE_ELECTIONS_PATH} did not return a list"
        )

    matches = [
        election
        for election in body
        if isinstance(election, Mapping) and election.get("title") == title
    ]

    if len(matches) > 1:
        raise ApiError(
            f"Election run {run}: found {len(matches)} active elections already "
            f"titled {title!r}. Refusing to guess which one the load test should "
            f"use, and refusing to create another. Nothing has been written to the "
            f"manifest — resolve the duplicates, or use a new PERF_BATCH."
        )

    return dict(matches[0]) if matches else None


def recover_committed_election(
    client: httpx.Client,
    config: PerfConfig,
    run: int,
    existing: Mapping[str, Any],
    manifest: dict[str, Any],
    manifest_file: Path,
    external_ids: Sequence[str],
    *,
    token: str,
    write: Writer,
) -> None:
    """Adopt an already-committed election into the manifest, or refuse.

    Validated with exactly the same checks a manifest election gets on every
    rerun — title, status, organizer, ballot configuration, the two candidates and
    the full set of 50 eligible voters — so a recovered entry is held to the same
    standard as a created one. Anything short of a complete match raises and
    leaves the manifest untouched.
    """
    # Raises unless the candidate list is exactly the two expected names.
    entry = summarize_election(existing, run)

    if entry["status"] != "active":
        raise ApiError(
            f"Election run {run} was found with status {entry['status']!r}, "
            f"expected 'active'"
        )

    # Re-reads the election and its eligibility list from the authoritative
    # single-election routes rather than trusting the search result.
    verify_existing_election(
        client,
        entry,
        config=config,
        external_ids=external_ids,
        token=token,
        write=lambda _message: None,
    )

    manifest["elections"].append(entry)
    common.save_manifest(manifest, manifest_file)

    write(
        f"Recovered election {run}/{common.ELECTION_COUNT} "
        f"({entry['title']}, {entry['election_id']}) — it had already been "
        f"committed by the server, most likely after a client timeout. "
        f"No new election was created."
    )


def create_elections(
    client: httpx.Client,
    config: PerfConfig,
    manifest: dict[str, Any],
    manifest_file: Path,
    token: str,
    *,
    write: Writer,
) -> None:
    """Create the three active elections, reusing any already in the manifest."""
    external_ids = common.manifest_external_ids(manifest)
    if len(external_ids) != common.VOTER_COUNT:
        raise ManifestError(
            f"Cannot create elections: the manifest holds {len(external_ids)} "
            f"voter external ids, expected {common.VOTER_COUNT}."
        )

    headers = common.auth_headers(token)

    for entry in manifest["elections"]:
        verify_existing_election(
            client,
            entry,
            config=config,
            external_ids=external_ids,
            token=token,
            write=write,
        )

    for run in range(len(manifest["elections"]) + 1, common.ELECTION_COUNT + 1):
        # A previous attempt may have timed out on the client while the server
        # committed. Adopt that election instead of creating a duplicate.
        already_committed = find_committed_election(client, config, run, token=token)
        if already_committed is not None:
            recover_committed_election(
                client,
                config,
                run,
                already_committed,
                manifest,
                manifest_file,
                external_ids,
                token=token,
                write=write,
            )
            continue

        payload = common.build_election_payload(
            run,
            config.batch,
            external_ids,
            duration_hours=config.election_duration_hours,
        )

        response = client.post(common.ELECTIONS_PATH, json=payload, headers=headers)
        if response.status_code != 201:
            raise ApiError(
                f"Election run {run}: unexpected {response.status_code} from "
                f"POST {common.ELECTIONS_PATH} — {common.short_detail(response)}"
            )

        entry = summarize_election(response.json(), run)
        if entry["status"] != "active":
            raise ApiError(
                f"Election run {run} was created with status "
                f"{entry['status']!r}, expected 'active'"
            )

        manifest["elections"].append(entry)
        common.save_manifest(manifest, manifest_file)

        write(
            f"Created election {run}/{common.ELECTION_COUNT} "
            f"({entry['title']}, {entry['election_id']})"
        )


# ── Orchestration ─────────────────────────────────────────────────────────────


def prepare_manifest(
    config: PerfConfig,
    staging_url: str,
    manifest_file: Path,
) -> dict[str, Any]:
    """Load and validate an existing manifest, or start a fresh one.

    A manifest from another batch or another deployment is refused here, before
    any request is made — overwriting it would destroy the only local record of
    accounts that exist on a server and cannot be deleted.
    """
    existing = common.load_manifest(manifest_file)

    if existing is None:
        return common.new_manifest(
            staging_url,
            config.batch,
            {
                "username": config.organizer_username,
                "email": config.organizer_email,
            },
        )

    common.validate_manifest(existing, batch=config.batch, base_url=staging_url)

    stored_email = existing["organizer"].get("email")
    if stored_email != config.organizer_email:
        raise ManifestError(
            f"Manifest organizer is {stored_email!r} but this run is configured "
            f"for {config.organizer_email!r}. Refusing to mix two organizers into "
            f"one batch."
        )

    existing.setdefault("voters", [])
    existing.setdefault("elections", [])
    return existing


def run_setup(
    config: PerfConfig,
    *,
    assume_yes: bool,
    transport: httpx.BaseTransport | None = None,
    data_dir: Path | None = None,
    write: Writer = _default_writer,
    prompt: Callable[[str], str] = input,
) -> Path:
    """Guards first, then the work. Returns the path of the manifest written.

    The ordering here is the safety property the tests pin down: nothing that
    could change server state happens until guards 1-8 have all passed.
    """
    # Guard 1 — armed at all.
    common.require_setup_allowed(config.setup_allowed)

    # Guards 2-5 — HTTPS, production supplied, different, and named like staging.
    staging_url = common.validate_target(
        config.base_url,
        config.production_base_url,
        local_allowed=config.local_test_allowed,
    )

    # Guard 7 — show exactly what is about to happen, before asking.
    write(common.describe_plan(config, staging_url))

    manifest_file = common.manifest_path(config.batch, data_dir)
    manifest = prepare_manifest(config, staging_url, manifest_file)

    remaining_voters = common.VOTER_COUNT - len(manifest["voters"])
    remaining_elections = common.ELECTION_COUNT - len(manifest["elections"])
    if remaining_voters < common.VOTER_COUNT or remaining_elections < common.ELECTION_COUNT:
        write(
            f"  Resuming batch {config.batch}: {remaining_voters} voters and "
            f"{remaining_elections} elections still to create.\n"
        )

    # Guard 6 — the operator confirms the target.
    common.confirm_target(staging_url, assume_yes=assume_yes, prompt=prompt)

    with common.build_client(
        staging_url, transport=transport, timeout=common.SETUP_TIMEOUT_SECONDS
    ) as client:
        # Guard 8 — the database is actually reachable.
        common.check_health(client)
        write("Health check passed: database connected.")

        token = ensure_organizer(client, config, write=write)

        create_voters(client, config, manifest, manifest_file, write=write)
        create_elections(client, config, manifest, manifest_file, token, write=write)

    write("")
    write(f"Done. {len(manifest['voters'])} voters, {len(manifest['elections'])} elections.")
    write(f"Manifest: {manifest_file}")
    write("Run verify_performance_data.py before starting the load test.")

    return manifest_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m performance_tests.setup_performance_data",
        description=(
            "Create staging performance-test data (1 organizer, 50 voters, "
            "3 active elections). Creates permanent records; there is no "
            "cleanup or reset mode."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive target confirmation. Every other guard still applies.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = common.load_config()
        run_setup(config, assume_yes=args.yes)
    except PerfError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
