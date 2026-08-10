"""Unit tests for the read-only verification script.

The central property is that verification cannot change anything: the recorded
traffic must contain no PUT, PATCH, DELETE or POST other than ``/auth/login``,
and the read-only client must refuse one outright if a future change tried.
"""

from __future__ import annotations

import json

import httpx
import pytest

from performance_tests import common, setup_performance_data as setup
from performance_tests import verify_performance_data as verify
from performance_tests.common import ReadOnlyViolationError, SafetyError

from .conftest import (
    BATCH,
    PRODUCTION_URL,
    STAGING_URL,
    base_env,
)


def seed_batch(api, config, data_dir, silent):
    """Run a full setup against the fake API so there is something to verify."""
    return setup.run_setup(
        config,
        assume_yes=True,
        transport=api.transport(),
        data_dir=data_dir,
        write=silent,
    )


def verify_run(api, config, data_dir, silent, **kwargs):
    return verify.run_verification(
        config,
        transport=api.transport(),
        data_dir=data_dir,
        write=silent,
        **kwargs,
    )


def load(data_dir):
    return json.loads(
        common.manifest_path(BATCH, data_dir).read_text(encoding="utf-8")
    )


def store(data_dir, manifest):
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))


# ── Happy path ────────────────────────────────────────────────────────────────


def test_prepared_batch_verifies_as_ready(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    api.requests.clear()

    report = verify_run(api, config, data_dir, silent)

    assert report.ok, report.failures
    assert "READY" in report.render()


def test_verification_checks_all_three_elections(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    api.requests.clear()

    verify_run(api, config, data_dir, silent)

    for entry in manifest["elections"]:
        assert f"GET /elections/{entry['election_id']}" in api.paths
        assert f"GET /elections/{entry['election_id']}/voters" in api.paths


# ── The read-only guarantee ───────────────────────────────────────────────────


def test_verification_performs_no_mutating_requests(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    api.requests.clear()

    verify_run(api, config, data_dir, silent)

    for request in api.requests:
        assert request.method not in {"PUT", "PATCH", "DELETE"}, request
        if request.method == "POST":
            # Authentication only. It creates no records.
            assert request.path == common.LOGIN_PATH, request

    assert [r.path for r in api.requests if r.method == "POST"] == [common.LOGIN_PATH]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/elections/"),
        ("POST", "/auth/register"),
        ("POST", "/votes/"),
        ("PUT", "/elections/abc"),
        ("PATCH", "/elections/abc/activate"),
        ("DELETE", "/elections/abc"),
    ],
)
def test_read_only_client_blocks_mutating_requests(api, method, path):
    """The guard raises before the request is handed to the transport."""
    with common.build_client(
        STAGING_URL, transport=api.transport(), read_only=True
    ) as client:
        with pytest.raises(ReadOnlyViolationError):
            client.request(method, path)

    assert api.requests == []


def test_read_only_client_allows_login_and_gets(api):
    with common.build_client(
        STAGING_URL, transport=api.transport(), read_only=True
    ) as client:
        client.get(common.HEALTH_PATH)
        client.post(common.LOGIN_PATH, json={"email": "x@test.com", "password": "y"})

    assert api.paths == [
        f"GET {common.HEALTH_PATH}",
        f"POST {common.LOGIN_PATH}",
    ]


def test_verification_never_writes_or_deletes_the_manifest(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest_file = common.manifest_path(BATCH, data_dir)
    before = manifest_file.read_bytes()
    mtime = manifest_file.stat().st_mtime_ns

    verify_run(api, config, data_dir, silent)

    assert manifest_file.read_bytes() == before
    assert manifest_file.stat().st_mtime_ns == mtime


# ── Target safety still applies to a read-only run ────────────────────────────


def test_verification_refuses_a_production_target(api, data_dir, silent):
    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: PRODUCTION_URL}), require_voter_password=False
    )

    with pytest.raises(SafetyError):
        verify_run(api, config, data_dir, silent)

    assert api.requests == []


def test_verification_refuses_a_non_https_target(api, data_dir, silent):
    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: "http://staging-api.example.com"}),
        require_voter_password=False,
    )

    with pytest.raises(SafetyError, match="must be HTTPS"):
        verify_run(api, config, data_dir, silent)

    assert api.requests == []


def test_verification_does_not_require_setup_allowed(api, config, data_dir, silent):
    """A read-only check changes nothing, so it is not gated on the arming flag."""
    seed_batch(api, config, data_dir, silent)

    disarmed = common.load_config(base_env(**{common.ENV_SETUP_ALLOWED: "false"}))
    api.requests.clear()

    report = verify_run(api, disarmed, data_dir, silent)

    assert report.ok, report.failures


def test_verification_fails_when_health_check_fails(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    api.healthy = False

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("Health check" in failure for failure in report.failures)


# ── Detection of broken data ──────────────────────────────────────────────────


def test_verification_detects_a_missing_manifest(api, config, data_dir, silent):
    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("exists" in failure for failure in report.failures)
    assert api.requests == []


def test_verification_detects_a_missing_voter(api, config, data_dir, silent):
    """A voter dropped from the election's eligibility list is caught."""
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    election_id = manifest["elections"][0]["election_id"]
    api.elections[election_id]["eligible"].pop()

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("every manifest voter is eligible" in f for f in report.failures)
    assert any("49 eligible voters" in f or "got 49" in f for f in report.failures)


def test_verification_detects_a_short_manifest(api, config, data_dir, silent):
    """Forty-nine recorded voters is an unfinished setup, not a ready data set."""
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    manifest["voters"].pop()
    store(data_dir, manifest)

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("49 voters" in f for f in report.failures)


def test_verification_detects_an_unexpected_eligible_voter(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    election_id = manifest["elections"][2]["election_id"]
    api.elections[election_id]["eligible"].append("VOT-99999")

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("no unexpected eligible voters" in f for f in report.failures)


def test_verification_detects_a_non_active_election(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    election_id = manifest["elections"][1]["election_id"]
    api.elections[election_id]["response"]["status"] = "completed"

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("status is active" in f for f in report.failures)


def test_verification_detects_a_voter_who_has_already_voted(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    election_id = manifest["elections"][0]["election_id"]
    stored = api.elections[election_id]
    stored["voted"].add(stored["eligible"][0])

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("no voter has voted" in f for f in report.failures)


def test_verification_detects_a_multi_select_ballot(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    election_id = manifest["elections"][0]["election_id"]
    api.elections[election_id]["response"]["ballot_type"] = "multi"
    api.elections[election_id]["response"]["max_selections"] = 2

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("single-choice ballot" in f for f in report.failures)
    assert any("max_selections == 1" in f for f in report.failures)


def test_verification_detects_a_wrong_candidate_set(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    election_id = manifest["elections"][0]["election_id"]
    api.elections[election_id]["response"]["candidates"].pop()

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("two expected candidates" in f for f in report.failures)


def test_verification_detects_an_expired_election(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    election_id = manifest["elections"][0]["election_id"]
    api.elections[election_id]["response"]["end_date"] = "2020-01-01T00:00:00"

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("end time is in the future" in f for f in report.failures)


def test_verification_detects_a_wrong_title(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    election_id = manifest["elections"][0]["election_id"]
    api.elections[election_id]["response"]["title"] = "Something else"

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("title is" in f for f in report.failures)


def test_verification_detects_an_unreachable_election(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    api.elections.pop(manifest["elections"][0]["election_id"])

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("readable by the organizer" in f for f in report.failures)


def test_verification_detects_duplicate_voters_in_the_manifest(api, config, data_dir, silent):
    """A manifest with a repeated external id is rejected by the schema check."""
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    manifest["voters"][10]["external_id"] = manifest["voters"][0]["external_id"]
    store(data_dir, manifest)

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("Duplicate voter" in f for f in report.failures)


def test_verification_rejects_a_manifest_from_another_batch(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    manifest["batch"] = "99999999"
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("batch" in f for f in report.failures)


def test_verification_rejects_a_manifest_from_another_deployment(
    api, config, data_dir, silent
):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    manifest["base_url"] = "https://performance-api.other.example.com"
    common.save_manifest(manifest, common.manifest_path(BATCH, data_dir))

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("two deployments" in f for f in report.failures)


def test_verification_fails_when_the_organizer_cannot_log_in(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    api.organizer_registered = False

    report = verify_run(api, config, data_dir, silent)

    assert not report.ok
    assert any("Organizer login" in f for f in report.failures)


# ── --check-logins ────────────────────────────────────────────────────────────


def test_voter_logins_are_not_checked_by_default(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    api.requests.clear()

    verify_run(api, config, data_dir, silent)

    logins = api.requests_to(common.LOGIN_PATH)
    assert len(logins) == 1  # the organizer only


def test_check_logins_authenticates_all_fifty_voters(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    api.requests.clear()

    report = verify_run(api, config, data_dir, silent, check_logins=True)

    logins = api.requests_to(common.LOGIN_PATH)
    assert len(logins) == 51  # organizer + 50 voters
    assert report.ok, report.failures
    assert "Checked login 050/050" in silent.lines


def test_check_logins_reports_a_failing_voter(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    # Drop one voter server-side so its login returns 401.
    del api.voters[manifest["voters"][3]["external_id"]]

    report = verify_run(api, config, data_dir, silent, check_logins=True)

    assert not report.ok
    assert any("voter logins succeed" in f for f in report.failures)


def test_check_logins_still_makes_no_mutating_request(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    api.requests.clear()

    verify_run(api, config, data_dir, silent, check_logins=True)

    assert {r.path for r in api.requests if r.method == "POST"} == {common.LOGIN_PATH}
    assert not any(r.method in {"PUT", "PATCH", "DELETE"} for r in api.requests)


def test_check_logins_requires_the_voter_password(api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)

    env = base_env()
    del env[common.ENV_VOTER_PASSWORD]
    without_password = common.load_config(env, require_voter_password=False)

    report = verify_run(api, without_password, data_dir, silent, check_logins=True)

    assert not report.ok
    assert any(common.ENV_VOTER_PASSWORD in f for f in report.failures)


# ── Report rendering and exit status ──────────────────────────────────────────


def test_report_renders_pass_and_fail_lines():
    report = verify.Report()
    report.require(True, "first")
    report.require(False, "second")

    rendered = report.render()

    assert "[PASS] first" in rendered
    assert "[FAIL] second" in rendered
    assert "NOT READY" in rendered
    assert report.ok is False


def _patch_main(monkeypatch, api, config, data_dir, silent):
    """Point main() at the fake API without letting it read a real environment.

    The original ``run_verification`` is captured before patching, so the
    replacement injects the mock transport instead of recursing into itself.
    """
    original = verify.run_verification

    monkeypatch.setattr(verify.common, "load_config", lambda **_: config)
    monkeypatch.setattr(
        verify,
        "run_verification",
        lambda cfg, **kwargs: original(
            cfg,
            transport=api.transport(),
            data_dir=data_dir,
            write=silent,
            **kwargs,
        ),
    )


def test_main_returns_nonzero_when_checks_fail(monkeypatch, api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)
    manifest = load(data_dir)
    api.elections[manifest["elections"][0]["election_id"]]["response"]["status"] = "draft"

    _patch_main(monkeypatch, api, config, data_dir, silent)

    assert verify.main([]) == 1


def test_main_returns_zero_when_everything_passes(monkeypatch, api, config, data_dir, silent):
    seed_batch(api, config, data_dir, silent)

    _patch_main(monkeypatch, api, config, data_dir, silent)

    assert verify.main([]) == 0
