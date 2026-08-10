"""Unit tests for the setup script.

Two properties matter most and are asserted repeatedly:

* when a guard refuses, ``api.mutating_requests`` is empty — nothing was created;
* nothing secret ever reaches the manifest on disk.

Every test drives an ``httpx.MockTransport``; none can reach a network.
"""

from __future__ import annotations

import json

import httpx
import pytest

from performance_tests import common, setup_performance_data as setup
from performance_tests.common import ApiError, ConfigError, ManifestError, SafetyError

from .conftest import (
    BATCH,
    FAKE_TOKEN,
    ORGANIZER_PASSWORD,
    PRODUCTION_URL,
    STAGING_URL,
    VOTER_PASSWORD,
    base_env,
)


def run(api, config, data_dir, write, **kwargs):
    return setup.run_setup(
        config,
        assume_yes=kwargs.pop("assume_yes", True),
        transport=api.transport(),
        data_dir=data_dir,
        write=write,
        **kwargs,
    )


# ── Guards: nothing is created when the target is wrong ───────────────────────


def test_missing_setup_allowed_blocks_execution(api, data_dir, silent):
    config = common.load_config(base_env(**{common.ENV_SETUP_ALLOWED: "false"}))

    with pytest.raises(SafetyError, match="PERF_SETUP_ALLOWED"):
        run(api, config, data_dir, silent)

    assert api.requests == []


@pytest.mark.parametrize("value", ["True", "TRUE", "1", "yes", "y", " true", ""])
def test_setup_allowed_requires_exact_lowercase_true(value):
    """Only the exact string arms the script — no truthiness, no normalisation."""
    with pytest.raises(SafetyError):
        common.require_setup_allowed(value)


def test_setup_allowed_unset_blocks_execution(api, data_dir, silent):
    env = base_env()
    del env[common.ENV_SETUP_ALLOWED]
    config = common.load_config(env)

    with pytest.raises(SafetyError):
        run(api, config, data_dir, silent)

    assert api.mutating_requests == []


def test_staging_equal_to_production_is_blocked(api, data_dir, silent):
    config = common.load_config(
        base_env(**{common.ENV_PRODUCTION_BASE_URL: STAGING_URL})
    )

    with pytest.raises(SafetyError, match="same target"):
        run(api, config, data_dir, silent)

    assert api.requests == []


def test_staging_equal_to_production_after_normalization_is_blocked():
    """Trailing slash, case and the default port must not defeat the comparison."""
    with pytest.raises(SafetyError, match="same target"):
        common.validate_target(
            "https://Staging-API.example.com:443/", "https://staging-api.example.com"
        )


def test_non_https_target_is_blocked(api, data_dir, silent):
    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: "http://staging-api.example.com"})
    )

    with pytest.raises(SafetyError, match="must be HTTPS"):
        run(api, config, data_dir, silent)

    assert api.requests == []


def test_url_without_staging_or_performance_is_blocked(api, data_dir, silent):
    # Distinct from the production URL, so this fails on the naming guard rather
    # than on the "same target" guard.
    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: "https://evoting-api.example.com"})
    )

    with pytest.raises(SafetyError, match="does not identify itself as a test target"):
        run(api, config, data_dir, silent)

    assert api.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "https://staging-api.example.com",
        "https://api-staging.example.com",
        "https://performance.example.com",
        "https://evoting-performance-api.example.com",
    ],
)
def test_recognised_staging_hostnames_pass(url):
    assert common.validate_target(url, PRODUCTION_URL) == common.normalize_base_url(url)


def test_missing_production_url_is_blocked():
    with pytest.raises(SafetyError, match="PERF_PRODUCTION_BASE_URL must be set"):
        common.validate_target(STAGING_URL, "")


def test_production_url_that_looks_like_staging_is_blocked():
    """Otherwise the "different from production" check compares two staging URLs."""
    with pytest.raises(SafetyError, match="looks like a staging URL"):
        common.validate_target(STAGING_URL, "https://staging2.example.com")


@pytest.mark.parametrize(
    "url",
    [
        "https://staging.example.com:abc",  # not a number
        "https://staging.example.com:99999",  # out of range 0-65535
        "https://staging.example.com:65536",  # one past the top of the range
        "https://staging.example.com:-1",  # negative
        "https://staging.example.com:8o80",  # transposed character
    ],
)
def test_malformed_port_is_refused_as_a_safety_error(url):
    """urlsplit only validates the port when it is read, so this must not escape.

    Left uncaught it surfaces as a raw ValueError traceback instead of the
    deliberate refusal every other bad target produces.
    """
    with pytest.raises(SafetyError, match="invalid port"):
        common.normalize_base_url(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://staging.example.com:", "https://staging.example.com"),
        ("https://staging.example.com:/", "https://staging.example.com"),
        ("https://staging.example.com:443", "https://staging.example.com"),
        ("https://staging.example.com:0443", "https://staging.example.com"),
        ("https://staging.example.com:8443", "https://staging.example.com:8443"),
    ],
)
def test_empty_and_valid_ports_normalize_without_error(url, expected):
    """An empty port is not malformed — urlsplit reports None — so it normalizes."""
    assert common.normalize_base_url(url) == expected


@pytest.mark.parametrize(
    "variable", [common.ENV_BASE_URL, common.ENV_PRODUCTION_BASE_URL]
)
def test_malformed_port_in_either_url_blocks_the_run(api, data_dir, silent, variable):
    """Whichever URL carries the bad port, nothing is created and nothing is sent."""
    config = common.load_config(
        base_env(**{variable: "https://staging.example.com:99999"})
    )

    with pytest.raises(SafetyError, match="invalid port"):
        run(api, config, data_dir, silent)

    assert api.requests == []


def test_malformed_port_is_refused_before_a_client_exists(monkeypatch, api, data_dir, silent):
    """The refusal happens in the guard layer, upstream of any client construction."""
    built: list[str] = []
    real_build = common.build_client

    def spy(*args, **kwargs):
        built.append("built")
        return real_build(*args, **kwargs)

    monkeypatch.setattr(common, "build_client", spy)

    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: "https://staging.example.com:abc"})
    )

    with pytest.raises(SafetyError, match="invalid port"):
        run(api, config, data_dir, silent)

    assert built == []
    assert api.requests == []


def test_verification_also_refuses_a_malformed_port(api, data_dir, silent):
    """The read-only script shares the guard, so it refuses identically."""
    from performance_tests import verify_performance_data as verify

    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: "https://staging.example.com:abc"}),
        require_voter_password=False,
    )

    with pytest.raises(SafetyError, match="invalid port"):
        verify.run_verification(
            config, transport=api.transport(), data_dir=data_dir, write=silent
        )

    assert api.requests == []


def test_health_check_failure_blocks_all_mutations(api, config, data_dir, silent):
    api.healthy = False

    with pytest.raises(SafetyError, match="database reported as"):
        run(api, config, data_dir, silent)

    assert api.mutating_requests == []
    assert api.paths == [f"GET {common.HEALTH_PATH}"]


def test_health_check_non_200_blocks_all_mutations(api, config, data_dir, silent):
    api.health_status = 503

    with pytest.raises(SafetyError, match="503"):
        run(api, config, data_dir, silent)

    assert api.mutating_requests == []


def test_confirmation_mismatch_blocks_execution(api, config, data_dir, silent):
    with pytest.raises(SafetyError, match="Confirmation did not match"):
        run(
            api,
            config,
            data_dir,
            silent,
            assume_yes=False,
            prompt=lambda _: "https://api.example.com",
        )

    assert api.requests == []


def test_confirmation_accepts_the_exact_target(api, config, data_dir, silent):
    manifest_file = run(
        api,
        config,
        data_dir,
        silent,
        assume_yes=False,
        prompt=lambda _: STAGING_URL,
    )

    assert manifest_file.exists()


def test_plan_is_printed_before_confirmation(api, config, data_dir, silent):
    """Guard 7: target, batch and volumes are visible before anything is asked."""
    seen: list[str] = []

    def prompt(_message: str) -> str:
        seen.extend(silent.lines)
        return STAGING_URL

    run(api, config, data_dir, silent, assume_yes=False, prompt=prompt)

    printed = "\n".join(seen)
    assert STAGING_URL in printed
    assert BATCH in printed
    assert "Organizer accounts  : 1" in printed
    assert "Voter accounts      : 50" in printed
    assert "Elections           : 3" in printed


# ── Voter payload generation ──────────────────────────────────────────────────


def test_exactly_fifty_correctly_named_voter_payloads():
    payloads = common.build_voter_payloads(BATCH, VOTER_PASSWORD)

    assert len(payloads) == 50
    assert payloads[0]["username"] == f"perf_voter_001_{BATCH}"
    assert payloads[0]["email"] == f"perf_voter_001_{BATCH}@test.com"
    assert payloads[-1]["username"] == f"perf_voter_050_{BATCH}"
    assert payloads[-1]["email"] == f"perf_voter_050_{BATCH}@test.com"

    assert {p["role"] for p in payloads} == {"voter"}
    assert {p["group"] for p in payloads} == {f"PERFORMANCE-TEST-USERS-{BATCH}"}
    assert len({p["username"] for p in payloads}) == 50
    assert len({p["email"] for p in payloads}) == 50


def test_password_is_sent_in_registration_but_not_stored(api, config, data_dir, silent):
    manifest_file = run(api, config, data_dir, silent)

    registrations = api.requests_to(common.REGISTER_PATH)
    assert len(registrations) == 51  # 1 organizer + 50 voters
    assert all(r.json_body["password"] for r in registrations)
    assert {
        r.json_body["password"] for r in registrations if r.json_body["role"] == "voter"
    } == {VOTER_PASSWORD}

    serialized = manifest_file.read_text(encoding="utf-8")
    assert VOTER_PASSWORD not in serialized
    assert ORGANIZER_PASSWORD not in serialized
    assert "password" not in serialized.lower()


def test_registration_stops_on_unexpected_api_failure(api, config, data_dir, silent):
    def fail_on_tenth(request, body):
        if body.get("username") == f"perf_voter_010_{BATCH}":
            return httpx.Response(500, json={"detail": "boom"})
        return None

    api.register_override = fail_on_tenth

    with pytest.raises(ApiError, match="unexpected 500"):
        run(api, config, data_dir, silent)

    manifest = json.loads(
        common.manifest_path(BATCH, data_dir).read_text(encoding="utf-8")
    )
    # The nine that succeeded are recorded; the failure did not roll them back and
    # did not invent an entry for the tenth.
    assert len(manifest["voters"]) == 9
    assert manifest["elections"] == []


def test_duplicate_registration_is_not_treated_as_success(api, config, data_dir, silent):
    """A 400 "Account already exists." carries no external_id, so it cannot pass."""

    def duplicate_on_fifth(request, body):
        if body.get("username") == f"perf_voter_005_{BATCH}":
            return httpx.Response(400, json={"detail": "Account already exists."})
        return None

    api.register_override = duplicate_on_fifth

    with pytest.raises(ApiError, match="not in the manifest"):
        run(api, config, data_dir, silent)

    manifest = json.loads(
        common.manifest_path(BATCH, data_dir).read_text(encoding="utf-8")
    )
    assert len(manifest["voters"]) == 4


def test_registration_response_mismatch_is_rejected(api, config, data_dir, silent):
    """A server that answers with a different account must not be recorded."""

    def wrong_username(request, body):
        if body.get("username") == f"perf_voter_003_{BATCH}":
            return httpx.Response(
                201,
                json={
                    "id": "00000000-0000-0000-0000-000000000001",
                    "role": "voter",
                    "status": "active",
                    "external_id": "VOT-99999",
                    "username": "somebody_else",
                    "email": body["email"],
                    "created_at": "2026-08-10T13:00:00",
                    "updated_at": "2026-08-10T13:00:00",
                },
            )
        return None

    api.register_override = wrong_username

    with pytest.raises(ApiError, match="not what was"):
        run(api, config, data_dir, silent)


def test_progress_is_reported_per_voter(api, config, data_dir, silent):
    run(api, config, data_dir, silent)

    assert "Created voter 001/050" in silent.lines
    assert "Created voter 050/050" in silent.lines


# ── Organizer workflow ────────────────────────────────────────────────────────


def test_existing_organizer_is_reused_not_reregistered(api, config, data_dir, silent):
    api.organizer_registered = True

    run(api, config, data_dir, silent)

    organizer_registrations = [
        r
        for r in api.requests_to(common.REGISTER_PATH)
        if r.json_body.get("role") == "organizer"
    ]
    assert organizer_registrations == []
    assert any("reusing it" in line for line in silent.lines)


def test_organizer_is_registered_when_login_returns_401(api, config, data_dir, silent):
    run(api, config, data_dir, silent)

    organizer_registrations = [
        r
        for r in api.requests_to(common.REGISTER_PATH)
        if r.json_body.get("role") == "organizer"
    ]
    assert len(organizer_registrations) == 1
    assert organizer_registrations[0].json_body["username"] == f"perf_organizer_{BATCH}"


def test_unexpected_login_status_is_not_read_as_missing_account(
    api, config, data_dir, silent
):
    """A 502 on login must fail loudly, not fall through to registration."""
    normal_handle = api.handle

    def broken_login(request: httpx.Request) -> httpx.Response:
        response = normal_handle(request)
        if request.url.path == common.LOGIN_PATH:
            return httpx.Response(502, json={"detail": "bad gateway"})
        return response

    api.transport = lambda: httpx.MockTransport(broken_login)

    with pytest.raises(ApiError, match="Unexpected 502"):
        run(api, config, data_dir, silent)

    assert api.requests_to(common.REGISTER_PATH) == []


# ── Manifest, checkpointing and resume ────────────────────────────────────────


def test_manifest_is_checkpointed_after_every_voter(
    api, config, data_dir, silent, monkeypatch
):
    """One atomic write per successful registration, each adding exactly one voter.

    Asserted on the bytes that actually landed on disk, so a future change that
    batched the writes — and so lost more than one account to a crash — fails here.
    """
    manifest_file = common.manifest_path(BATCH, data_dir)
    voter_counts_on_disk: list[int] = []

    real_save = common.save_manifest

    def spy(manifest, path):
        real_save(manifest, path)
        stored = json.loads(manifest_file.read_text(encoding="utf-8"))
        voter_counts_on_disk.append(len(stored["voters"]))

    monkeypatch.setattr(common, "save_manifest", spy)

    run(api, config, data_dir, silent)

    # The first 50 writes are the voters: after voter N the file holds N voters.
    assert voter_counts_on_disk[:50] == list(range(1, 51))
    # The remaining writes are the three elections, which add no voters.
    assert voter_counts_on_disk[50:] == [50, 50, 50]


def test_partial_manifest_resumes_at_the_correct_voter(api, config, data_dir, silent):
    """Stop after voter 23; the next run must start at voter 24 and create 27."""
    def fail_after_23(request, body):
        username = body.get("username", "")
        if username == f"perf_voter_024_{BATCH}":
            return httpx.Response(503, json={"detail": "service unavailable"})
        return None

    api.register_override = fail_after_23

    with pytest.raises(ApiError):
        run(api, config, data_dir, silent)

    manifest_file = common.manifest_path(BATCH, data_dir)
    assert len(json.loads(manifest_file.read_text(encoding="utf-8"))["voters"]) == 23

    # Second run: the server is healthy again and the organizer already exists.
    api.register_override = None
    api.requests.clear()

    run(api, config, data_dir, silent)

    voter_registrations = [
        r
        for r in api.requests_to(common.REGISTER_PATH)
        if r.json_body.get("role") == "voter"
    ]
    assert len(voter_registrations) == 27
    assert voter_registrations[0].json_body["username"] == f"perf_voter_024_{BATCH}"
    assert voter_registrations[-1].json_body["username"] == f"perf_voter_050_{BATCH}"

    final = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert len(final["voters"]) == 50
    assert [v["username"] for v in final["voters"]] == [
        common.voter_username(i, BATCH) for i in range(1, 51)
    ]


def test_conflicting_manifest_base_url_is_rejected(api, config, data_dir, silent):
    manifest_file = common.manifest_path(BATCH, data_dir)
    manifest = common.new_manifest(
        "https://performance-api.other.example.com",
        BATCH,
        {"username": f"perf_organizer_{BATCH}", "email": f"perf_organizer_{BATCH}@test.com"},
    )
    common.save_manifest(manifest, manifest_file)

    with pytest.raises(ManifestError, match="Refusing to mix data"):
        run(api, config, data_dir, silent)

    assert api.mutating_requests == []


def test_conflicting_manifest_batch_is_rejected(api, config, data_dir, silent):
    manifest_file = common.manifest_path(BATCH, data_dir)
    manifest = common.new_manifest(
        STAGING_URL,
        "99999999",
        {"username": "perf_organizer_99999999", "email": "perf_organizer_99999999@test.com"},
    )
    common.save_manifest(manifest, manifest_file)

    with pytest.raises(ManifestError, match="Refusing to overwrite another batch"):
        run(api, config, data_dir, silent)

    assert api.mutating_requests == []


def test_out_of_order_manifest_is_rejected(api, config, data_dir, silent):
    """An entry that is not voter N at position N would break the resume cursor."""
    manifest_file = common.manifest_path(BATCH, data_dir)
    manifest = common.new_manifest(
        STAGING_URL,
        BATCH,
        {"username": f"perf_organizer_{BATCH}", "email": f"perf_organizer_{BATCH}@test.com"},
    )
    manifest["voters"] = [
        {
            "username": common.voter_username(7, BATCH),
            "email": common.voter_email(7, BATCH),
            "external_id": "VOT-00007",
        }
    ]
    common.save_manifest(manifest, manifest_file)

    with pytest.raises(ManifestError, match="out of order"):
        run(api, config, data_dir, silent)

    assert api.mutating_requests == []


def test_manifest_write_is_atomic(data_dir):
    """A temp file is used and replaced; no .tmp file survives a successful write."""
    manifest_file = common.manifest_path(BATCH, data_dir)
    manifest = common.new_manifest(STAGING_URL, BATCH, {"username": "u", "email": "e@test.com"})

    common.save_manifest(manifest, manifest_file)

    assert manifest_file.exists()
    assert list(data_dir.glob("*.tmp")) == []


def test_manifest_write_refuses_secrets(data_dir):
    manifest = common.new_manifest(STAGING_URL, BATCH, {"username": "u", "email": "e@test.com"})
    manifest["voters"].append(
        {
            "username": common.voter_username(1, BATCH),
            "email": common.voter_email(1, BATCH),
            "external_id": "VOT-00001",
            "password": "should-never-be-here",
        }
    )

    with pytest.raises(ManifestError, match="must never be persisted"):
        common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))


@pytest.mark.parametrize(
    "leak",
    [
        {"access_token": FAKE_TOKEN},
        {"jwt": "x"},
        {"database_url": "postgresql://user:pw@host/db"},
        {"supabase_key": "x"},
        {"organizer_password": "x"},
        {"private_key": "x"},
        {"harmless_looking": FAKE_TOKEN},
        {"note": "postgresql://user:pw@host/db"},
    ],
)
def test_secret_scanner_catches_forbidden_values(leak):
    manifest = common.new_manifest(STAGING_URL, BATCH, {"username": "u", "email": "e@test.com"})
    manifest["elections"].append({"run": 1, **leak})

    assert common.find_secret_leaks(manifest)


def test_organizer_password_and_jwt_never_appear_in_manifest(
    api, config, data_dir, silent
):
    manifest_file = run(api, config, data_dir, silent)
    serialized = manifest_file.read_text(encoding="utf-8")

    assert ORGANIZER_PASSWORD not in serialized
    assert VOTER_PASSWORD not in serialized
    assert FAKE_TOKEN not in serialized
    assert "Bearer" not in serialized
    assert common.find_secret_leaks(json.loads(serialized)) == []


def test_manifest_records_only_the_permitted_voter_fields(api, config, data_dir, silent):
    manifest_file = run(api, config, data_dir, silent)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert set(manifest["organizer"]) == {"username", "email"}
    for voter in manifest["voters"]:
        assert set(voter) == {"username", "email", "external_id"}


# ── Elections ─────────────────────────────────────────────────────────────────


def test_exactly_three_election_payloads_are_generated():
    external_ids = [f"VOT-{i:05d}" for i in range(1, 51)]
    payloads = common.build_election_payloads(BATCH, external_ids)

    assert len(payloads) == 3
    assert [p["title"] for p in payloads] == [
        f"PERF-{BATCH}-RUN-01",
        f"PERF-{BATCH}-RUN-02",
        f"PERF-{BATCH}-RUN-03",
    ]


def test_each_election_payload_contains_all_fifty_external_ids():
    external_ids = [f"VOT-{i:05d}" for i in range(1, 51)]
    payloads = common.build_election_payloads(BATCH, external_ids)

    for payload in payloads:
        assert payload["eligible_voter_external_ids"] == external_ids
        assert len(payload["eligible_voter_external_ids"]) == 50


def test_election_payload_is_single_choice_with_two_candidates():
    external_ids = [f"VOT-{i:05d}" for i in range(1, 51)]
    payload = common.build_election_payload(1, BATCH, external_ids)

    assert payload["ballot_type"] == "single"
    assert payload["max_selections"] == 1
    assert [c["name"] for c in payload["candidates"]] == [
        "Performance Candidate A",
        "Performance Candidate B",
    ]


def test_election_payload_uses_naive_sgt_timestamps():
    """An offset would make the backend compare aware against naive and fail."""
    external_ids = [f"VOT-{i:05d}" for i in range(1, 51)]
    payload = common.build_election_payload(1, BATCH, external_ids, duration_hours=24)

    start = payload["start_date"]
    end = payload["end_date"]

    assert "+" not in start and not start.endswith("Z")
    assert "+" not in end and not end.endswith("Z")

    start_dt = common.parse_api_datetime(start)
    end_dt = common.parse_api_datetime(end)
    now = common.now_sgt()

    assert start_dt < now  # backdated five minutes, so voting is open immediately
    assert (now - start_dt).total_seconds() == pytest.approx(300, abs=30)
    assert (end_dt - start_dt).total_seconds() == pytest.approx(
        (24 * 3600) + 300, abs=30
    )


def test_election_payload_rejects_a_wrong_number_of_voters():
    with pytest.raises(ConfigError, match="exactly 50"):
        common.build_election_payload(1, BATCH, ["VOT-00001"])


def test_election_payload_rejects_duplicate_external_ids():
    external_ids = [f"VOT-{i:05d}" for i in range(1, 50)] + ["VOT-00001"]
    with pytest.raises(ConfigError, match="duplicates"):
        common.build_election_payload(1, BATCH, external_ids)


def test_full_run_creates_three_active_elections(api, config, data_dir, silent):
    manifest_file = run(api, config, data_dir, silent)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert len(manifest["elections"]) == 3
    for run_number, entry in enumerate(manifest["elections"], start=1):
        assert entry["run"] == run_number
        assert entry["status"] == "active"
        assert entry["title"] == f"PERF-{BATCH}-RUN-{run_number:02d}"
        assert [c["name"] for c in entry["candidates"]] == list(common.CANDIDATE_NAMES)
        assert entry["candidate_id"] == entry["candidates"][0]["id"]

    created = [r for r in api.requests_to(common.ELECTIONS_PATH) if r.method == "POST"]
    assert len(created) == 3
    for request in created:
        assert len(request.json_body["eligible_voter_external_ids"]) == 50
        assert request.headers["authorization"] == f"Bearer {FAKE_TOKEN}"


def test_elections_are_created_directly_not_as_drafts(api, config, data_dir, silent):
    run(api, config, data_dir, silent)

    assert not any("/draft" in path for path in api.paths)
    assert not any("/activate" in path for path in api.paths)


def test_existing_matching_election_is_verified_and_skipped(api, config, data_dir, silent):
    run(api, config, data_dir, silent)
    api.requests.clear()

    # Rerunning the completed batch must create nothing.
    run(api, config, data_dir, silent)

    assert [r for r in api.requests_to(common.ELECTIONS_PATH) if r.method == "POST"] == []
    assert [r for r in api.requests_to(common.REGISTER_PATH)] == []
    assert any("already exists and matches" in line for line in silent.lines)


def test_mismatched_existing_election_stops_rather_than_duplicating(
    api, config, data_dir, silent
):
    manifest_file = run(api, config, data_dir, silent)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    # Simulate the election having been closed since it was created.
    election_id = manifest["elections"][0]["election_id"]
    api.elections[election_id]["response"]["status"] = "completed"
    api.requests.clear()

    with pytest.raises(ManifestError, match="does not match what the manifest claims"):
        run(api, config, data_dir, silent)

    assert [r for r in api.requests_to(common.ELECTIONS_PATH) if r.method == "POST"] == []


def test_missing_existing_election_stops_rather_than_recreating(
    api, config, data_dir, silent
):
    manifest_file = run(api, config, data_dir, silent)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    api.elections.pop(manifest["elections"][1]["election_id"])
    api.requests.clear()

    with pytest.raises(ManifestError, match="Refusing to create a replacement"):
        run(api, config, data_dir, silent)


# ── Configuration ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "variable", [common.ENV_ORGANIZER_PASSWORD, common.ENV_VOTER_PASSWORD]
)
def test_passwords_have_no_default(variable):
    env = base_env()
    del env[variable]

    with pytest.raises(ConfigError, match="no default"):
        common.load_config(env)


@pytest.mark.parametrize(
    "variable", [common.ENV_ORGANIZER_PASSWORD, common.ENV_VOTER_PASSWORD]
)
def test_short_passwords_are_rejected_locally(variable):
    """Caught before the first request, not as a 422 halfway through the run."""
    with pytest.raises(ConfigError, match="at least 8 characters"):
        common.load_config(base_env(**{variable: "short"}))


def test_organizer_defaults_are_batch_derived():
    env = base_env()
    del env[common.ENV_ORGANIZER_EMAIL]
    del env[common.ENV_ORGANIZER_USERNAME]

    config = common.load_config(env)

    assert config.organizer_username == f"perf_organizer_{BATCH}"
    assert config.organizer_email == f"perf_organizer_{BATCH}@test.com"


def test_duration_defaults_to_twenty_four_hours():
    env = base_env()
    del env[common.ENV_ELECTION_DURATION_HOURS]

    assert common.load_config(env).election_duration_hours == 24


def test_default_batch_is_alphanumeric_and_valid():
    assert common.validate_batch(common.default_batch()) == common.default_batch()


@pytest.mark.parametrize("batch", ["has space", "has-dash", "has_underscore", "", "a" * 25])
def test_invalid_batch_is_rejected(batch):
    with pytest.raises(ConfigError):
        common.validate_batch(batch)


def test_overlong_batch_group_name_is_rejected():
    """Defensive: the group column is 50 chars, and the batch is what fills it.

    ``validate_batch`` caps the batch at 24 characters, which keeps the generated
    group at 47 — so this check is unreachable through normal configuration. It is
    asserted directly so that raising the batch cap later fails here rather than
    as a 422 on voter 001.
    """
    with pytest.raises(ConfigError, match="over the backend"):
        common.voter_group("A" * 40)


# ── No accidental network access ──────────────────────────────────────────────


def test_client_without_transport_is_refused_by_the_test_harness():
    """Proves the autouse guard in conftest actually fires."""
    with pytest.raises(AssertionError, match="never touch the network"):
        common.build_client(STAGING_URL)
