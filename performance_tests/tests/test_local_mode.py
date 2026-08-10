"""Tests for loopback-only local testing mode (PERF_LOCAL_TEST_ALLOWED).

Two properties are asserted throughout:

* arming local mode permits **only** loopback — it does not widen what is
  reachable, it swaps one narrow rule for another;
* leaving it unset or false preserves the staging rules byte for byte.

Everything is mocked. Target validation is pure and makes no requests at all;
the script-level tests drive ``httpx.MockTransport`` through the shared FakeApi.
"""

from __future__ import annotations

import json

import pytest

from performance_tests import common, load_plan as lp, setup_performance_data as setup
from performance_tests import verify_performance_data as verify
from performance_tests.common import ConfigError, ManifestError, SafetyError

from .conftest import BATCH, PRODUCTION_URL, STAGING_URL, base_env

LOCAL_URL = "http://127.0.0.1:8000"
LOCAL_BATCH = "FYPLOCAL01"


def local_env(**overrides):
    env = base_env(
        **{
            common.ENV_BASE_URL: LOCAL_URL,
            common.ENV_LOCAL_TEST_ALLOWED: "true",
        }
    )
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


# ── The flag itself ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [None, ""])
def test_unset_flag_means_off(value):
    assert common.parse_local_test_allowed(value) is False


def test_false_means_off():
    assert common.parse_local_test_allowed("false") is False


def test_exact_true_arms_local_mode():
    assert common.parse_local_test_allowed("true") is True


@pytest.mark.parametrize(
    "value", ["TRUE", "True", "1", "yes", "y", "true ", " true", "True ", "on", "0"]
)
def test_ambiguous_flag_values_are_rejected(value):
    """A user who typed TRUE believes local mode is armed; say so explicitly."""
    with pytest.raises(ConfigError, match="must be exactly 'true' or 'false'"):
        common.parse_local_test_allowed(value)


def test_flag_is_carried_on_the_config():
    assert common.load_config(local_env()).local_test_allowed is True
    assert common.load_config(base_env()).local_test_allowed is False


# ── Loopback identity ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "host", ["localhost", "LOCALHOST", "127.0.0.1", "127.0.0.53", "127.1.2.3", "::1"]
)
def test_loopback_hosts_are_recognised(host):
    assert common.is_loopback_host(host) is True


@pytest.mark.parametrize(
    "host",
    [
        "localhost.example.com",  # deceptive suffix
        "notlocalhost",  # deceptive prefix
        "mylocalhost",
        "localhost.evil.co",
        "127.0.0.1.evil.com",  # looks like an IP, is a hostname
        "0.0.0.0",  # unspecified, not loopback
        "192.168.1.10",
        "192.168.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "8.8.8.8",
        "203.0.113.10",
        "api.example.com",
        "",
        None,
    ],
)
def test_non_loopback_hosts_are_rejected(host):
    """Never substring matching — that is what makes the deceptive names safe."""
    assert common.is_loopback_host(host) is False


# ── Local mode OFF: staging rules unchanged ───────────────────────────────────


def test_local_http_is_refused_when_the_flag_is_absent():
    with pytest.raises(SafetyError, match="must be HTTPS"):
        common.validate_target(LOCAL_URL, PRODUCTION_URL)


def test_local_http_is_refused_when_the_flag_is_false():
    with pytest.raises(SafetyError, match="must be HTTPS"):
        common.validate_target(LOCAL_URL, PRODUCTION_URL, local_allowed=False)


def test_https_localhost_is_still_refused_when_local_mode_is_off():
    """Loopback over HTTPS is still not a staging-named host."""
    with pytest.raises(SafetyError, match="does not identify itself"):
        common.validate_target("https://localhost:8000", PRODUCTION_URL)


def test_normal_https_staging_target_still_works_with_local_mode_off():
    assert common.validate_target(STAGING_URL, PRODUCTION_URL) == STAGING_URL


def test_validate_target_defaults_to_staging_rules():
    """The default argument is what keeps every un-migrated call site safe."""
    import inspect

    signature = inspect.signature(common.validate_target)

    assert signature.parameters["local_allowed"].default is False


# ── Local mode ON: loopback only ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
        ("http://localhost:8000", "http://localhost:8000"),
        ("http://127.0.0.1:8000/", "http://127.0.0.1:8000"),
        ("http://LOCALHOST:8000", "http://localhost:8000"),
        ("http://127.0.0.1", "http://127.0.0.1"),
        ("https://127.0.0.1:8443", "https://127.0.0.1:8443"),
        ("http://[::1]:8000", "http://[::1]:8000"),
    ],
)
def test_loopback_targets_are_accepted_in_local_mode(url, expected):
    assert common.validate_target(url, PRODUCTION_URL, local_allowed=True) == expected


def test_ipv6_loopback_normalizes_with_brackets():
    """Without re-bracketing, '::1' plus a port would build an unusable URL."""
    normalized = common.normalize_base_url("http://[::1]:8000")

    assert normalized == "http://[::1]:8000"
    # Round-trips: normalizing the normalized form is stable.
    assert common.normalize_base_url(normalized) == normalized


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost.example.com:8000",
        "http://notlocalhost:8000",
        "http://0.0.0.0:8000",
        "https://0.0.0.0:8000",
        "http://192.168.1.10:8000",
        "http://192.168.0.50",
        "http://10.0.0.5:8000",
        "http://172.16.0.1:8000",
        "http://8.8.8.8",
        "http://203.0.113.10:8000",
        "http://api.example.com:8000",
        "https://api-staging.example.com",
        "https://performance.example.com",
        "http://staging-api.example.com",
    ],
)
def test_non_loopback_targets_are_refused_in_local_mode(url):
    """Public HTTP *and* HTTPS are both refused: local mode means this machine."""
    with pytest.raises(SafetyError, match="only a loopback target"):
        common.validate_target(url, PRODUCTION_URL, local_allowed=True)


def test_path_or_query_containing_localhost_does_not_make_a_target_loopback():
    for url in (
        "https://evil.example.com/localhost",
        "https://evil.example.com/?host=localhost",
        "https://evil.example.com/127.0.0.1",
    ):
        with pytest.raises(SafetyError, match="only a loopback target"):
            common.validate_target(url, PRODUCTION_URL, local_allowed=True)


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@localhost:8000",
        "http://user@127.0.0.1:8000",
        "http://:secret@localhost:8000",
    ],
)
def test_credentials_in_the_url_are_refused(url):
    """The hostname of these is still 'localhost', so this needs its own check."""
    with pytest.raises(SafetyError, match="must not embed a username or password"):
        common.validate_target(url, PRODUCTION_URL, local_allowed=True)


# ── Rules that hold in BOTH modes ─────────────────────────────────────────────


def test_production_is_still_required_in_local_mode():
    with pytest.raises(SafetyError, match="PERF_PRODUCTION_BASE_URL must be set"):
        common.validate_target(LOCAL_URL, "", local_allowed=True)


def test_a_target_equal_to_production_is_still_refused_in_local_mode():
    with pytest.raises(SafetyError, match="same target"):
        common.validate_target(LOCAL_URL, LOCAL_URL, local_allowed=True)


def test_production_refusal_is_unchanged_in_both_modes():
    """Production is refused either way; only the stated reason differs.

    With local mode off it is caught as "same target". With local mode on the
    loopback rule catches it first and names the real problem — the production
    host is not this machine — which is the more precise refusal of the two.
    """
    with pytest.raises(SafetyError, match="same target"):
        common.validate_target(PRODUCTION_URL, PRODUCTION_URL, local_allowed=False)

    with pytest.raises(SafetyError, match="only a loopback target"):
        common.validate_target(PRODUCTION_URL, PRODUCTION_URL, local_allowed=True)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:abc",
        "http://127.0.0.1:99999",
        "http://localhost:65536",
        "http://localhost:-1",
    ],
)
def test_malformed_port_refusal_is_unchanged_in_local_mode(url):
    with pytest.raises(SafetyError, match="invalid port"):
        common.validate_target(url, PRODUCTION_URL, local_allowed=True)


@pytest.mark.parametrize("url", ["127.0.0.1:8000", "localhost:8000", "not a url", ""])
def test_malformed_urls_are_refused_in_local_mode(url):
    with pytest.raises(SafetyError):
        common.validate_target(url, PRODUCTION_URL, local_allowed=True)


def test_production_that_looks_like_staging_is_still_refused_in_local_mode():
    with pytest.raises(SafetyError, match="looks like a staging URL"):
        common.validate_target(
            LOCAL_URL, "https://staging2.example.com", local_allowed=True
        )


# ── Locust --host ─────────────────────────────────────────────────────────────


def test_locust_host_must_equal_the_configured_loopback_url():
    with pytest.raises(SafetyError, match=r"--host .* does not match"):
        lp.require_host_matches("http://127.0.0.1:9999", LOCAL_URL)


def test_locust_host_cannot_redirect_a_local_run_to_a_remote_target():
    for host in (STAGING_URL, PRODUCTION_URL, "http://192.168.1.10:8000"):
        with pytest.raises(SafetyError, match=r"--host"):
            lp.require_host_matches(host, LOCAL_URL)


def test_locust_host_cannot_redirect_a_staging_run_to_loopback():
    with pytest.raises(SafetyError, match=r"--host"):
        lp.require_host_matches(LOCAL_URL, STAGING_URL)


def test_matching_locust_host_is_accepted_for_a_local_run():
    lp.require_host_matches("http://127.0.0.1:8000/", LOCAL_URL)


# ── Script-level plumbing ─────────────────────────────────────────────────────


def test_setup_refuses_a_local_target_before_building_a_client(
    monkeypatch, api, data_dir, silent
):
    """Not armed: the refusal happens upstream of any client or request."""
    built: list[str] = []
    real_build = common.build_client
    monkeypatch.setattr(
        common,
        "build_client",
        lambda *a, **k: (built.append("built"), real_build(*a, **k))[1],
    )

    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: LOCAL_URL})  # local flag absent
    )

    with pytest.raises(SafetyError, match="must be HTTPS"):
        setup.run_setup(
            config,
            assume_yes=True,
            transport=api.transport(),
            data_dir=data_dir,
            write=silent,
        )

    assert built == []
    assert api.requests == []


def test_verification_refuses_a_local_target_without_any_request(
    api, data_dir, silent
):
    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: LOCAL_URL}), require_voter_password=False
    )

    with pytest.raises(SafetyError, match="must be HTTPS"):
        verify.run_verification(
            config, transport=api.transport(), data_dir=data_dir, write=silent
        )

    assert api.requests == []


def test_vote_run_verification_refuses_a_local_target_without_any_request(
    api, data_dir, silent
):
    config = common.load_config(
        base_env(**{common.ENV_BASE_URL: LOCAL_URL}), require_voter_password=False
    )

    with pytest.raises(SafetyError, match="must be HTTPS"):
        verify.run_vote_run_verification(
            config, 1, transport=api.transport(), data_dir=data_dir, write=silent
        )

    assert api.requests == []


def test_load_plan_refuses_a_local_target_when_not_armed(api, data_dir):
    env = base_env(**{common.ENV_BASE_URL: LOCAL_URL, lp.ENV_SCENARIO: "read"})

    with pytest.raises(SafetyError, match="must be HTTPS"):
        lp.build_plan(env, data_dir=data_dir)


def test_setup_still_requires_the_setup_flag_in_local_mode(api, data_dir, silent):
    """Local mode arms the target, not the creation of accounts."""
    config = common.load_config(
        local_env(**{common.ENV_SETUP_ALLOWED: "false", common.ENV_BATCH: LOCAL_BATCH})
    )

    with pytest.raises(SafetyError, match="PERF_SETUP_ALLOWED"):
        setup.run_setup(
            config,
            assume_yes=True,
            transport=api.transport(),
            data_dir=data_dir,
            write=silent,
        )

    assert api.requests == []


# ── A complete local batch, and manifest separation ───────────────────────────


@pytest.fixture
def local_manifest(api, data_dir, silent):
    """A full FYPLOCAL01 batch created against the loopback target."""
    config = common.load_config(local_env(**{common.ENV_BATCH: LOCAL_BATCH}))
    setup.run_setup(
        config,
        assume_yes=True,
        transport=api.transport(),
        data_dir=data_dir,
        write=silent,
    )
    return json.loads(
        common.manifest_path(LOCAL_BATCH, data_dir).read_text(encoding="utf-8")
    )


def test_a_local_batch_stores_the_normalized_loopback_url(local_manifest):
    assert local_manifest["base_url"] == "http://127.0.0.1:8000"
    assert local_manifest["batch"] == LOCAL_BATCH
    assert len(local_manifest["voters"]) == 50
    assert len(local_manifest["elections"]) == 3


def test_a_local_manifest_holds_no_secrets(local_manifest):
    assert common.find_secret_leaks(local_manifest) == []


def test_a_render_command_cannot_use_a_local_manifest(local_manifest, data_dir):
    """Same batch name, staging target: the base_url mismatch stops it."""
    env = base_env(
        **{
            common.ENV_BATCH: LOCAL_BATCH,
            common.ENV_BASE_URL: STAGING_URL,
            lp.ENV_SCENARIO: "read",
        }
    )

    with pytest.raises(ManifestError, match="two deployments"):
        lp.build_plan(env, data_dir=data_dir)


def test_a_local_command_cannot_use_a_render_manifest(api, config, data_dir, silent):
    """The reverse direction: a staging manifest is refused by a local run."""
    setup.run_setup(
        config,
        assume_yes=True,
        transport=api.transport(),
        data_dir=data_dir,
        write=silent,
    )

    env = local_env(**{common.ENV_BATCH: BATCH, lp.ENV_SCENARIO: "read"})

    with pytest.raises(ManifestError, match="two deployments"):
        lp.build_plan(env, data_dir=data_dir)


def test_local_setup_refuses_to_resume_a_render_manifest(
    api, config, data_dir, silent
):
    setup.run_setup(
        config,
        assume_yes=True,
        transport=api.transport(),
        data_dir=data_dir,
        write=silent,
    )
    api.requests.clear()

    local_config = common.load_config(local_env(**{common.ENV_BATCH: BATCH}))

    with pytest.raises(ManifestError, match="Refusing to mix data"):
        setup.run_setup(
            local_config,
            assume_yes=True,
            transport=api.transport(),
            data_dir=data_dir,
            write=silent,
        )

    assert api.mutating_requests == []


def test_local_verification_runs_against_the_local_manifest(
    local_manifest, api, data_dir, silent
):
    config = common.load_config(
        local_env(**{common.ENV_BATCH: LOCAL_BATCH}), require_voter_password=False
    )

    report = verify.run_verification(
        config, transport=api.transport(), data_dir=data_dir, write=silent
    )

    assert report.ok, report.failures


def test_local_vote_run_verification_works(local_manifest, api, data_dir, silent):
    config = common.load_config(
        local_env(**{common.ENV_BATCH: LOCAL_BATCH}), require_voter_password=False
    )

    report = verify.run_vote_run_verification(
        config, 1, transport=api.transport(), data_dir=data_dir, write=silent
    )

    assert report.ok, report.failures


# ── The vote and read scenarios are unchanged by local mode ───────────────────


def local_vote_env(run="1", **overrides):
    env = local_env(
        **{
            common.ENV_BATCH: LOCAL_BATCH,
            lp.ENV_SCENARIO: "vote",
            lp.ENV_VOTE_LOAD_ALLOWED: "true",
            lp.ENV_VOTE_ELECTION_RUN: run,
        }
    )
    env.update(overrides)
    return env


def test_local_vote_still_requires_the_vote_arming_flag(local_manifest, data_dir):
    env = local_vote_env()
    del env[lp.ENV_VOTE_LOAD_ALLOWED]

    with pytest.raises(SafetyError, match="Vote load is disabled"):
        lp.build_plan(env, data_dir=data_dir)


@pytest.mark.parametrize("value", ["TRUE", "1", "yes", "true ", "false"])
def test_local_vote_arming_still_requires_exact_true(local_manifest, data_dir, value):
    with pytest.raises(SafetyError, match="Vote load is disabled"):
        lp.build_plan(
            local_vote_env(**{lp.ENV_VOTE_LOAD_ALLOWED: value}), data_dir=data_dir
        )


@pytest.mark.parametrize(("run", "users"), [("1", 10), ("2", 25), ("3", 50)])
def test_local_vote_keeps_the_run_user_mapping(local_manifest, data_dir, run, users):
    plan = lp.build_plan(local_vote_env(run), data_dir=data_dir)

    assert plan.expected_voters == users
    assert lp.require_run_user_count(int(run), users) == users


@pytest.mark.parametrize(("run", "users"), [("1", 50), ("2", 10), ("3", 25)])
def test_local_vote_refuses_a_mismatched_cohort(local_manifest, data_dir, run, users):
    plan = lp.build_plan(local_vote_env(run), data_dir=data_dir)

    with pytest.raises(SafetyError, match="must be voted by exactly"):
        lp.require_run_user_count(int(plan.vote_election["run"]), users)


def test_local_vote_still_refuses_distributed_execution(local_manifest, data_dir):
    class Options:
        master = True
        worker = False
        processes = None

    with pytest.raises(SafetyError, match="distributed master"):
        lp.refuse_distributed(Options())


def test_local_read_scenario_is_unchanged(local_manifest, data_dir):
    plan = lp.build_plan(
        local_env(**{common.ENV_BATCH: LOCAL_BATCH, lp.ENV_SCENARIO: "read"}),
        data_dir=data_dir,
    )

    assert plan.scenario == lp.SCENARIO_READ
    assert plan.base_url == LOCAL_URL
    assert (plan.min_wait, plan.max_wait) == (1.0, 3.0)
    assert len(plan.voters) == 50
    assert len(plan.election_ids) == 3
    assert plan.vote_election is None


def test_local_plan_repr_still_hides_the_password(local_manifest, data_dir):
    plan = lp.build_plan(
        local_env(**{common.ENV_BATCH: LOCAL_BATCH, lp.ENV_SCENARIO: "read"}),
        data_dir=data_dir,
    )

    assert base_env()[common.ENV_VOTER_PASSWORD] not in repr(plan)


# ── No real network ───────────────────────────────────────────────────────────


def test_target_validation_makes_no_requests(api):
    """Validation is pure: it is decided entirely from its arguments."""
    common.validate_target(LOCAL_URL, PRODUCTION_URL, local_allowed=True)
    common.validate_target(STAGING_URL, PRODUCTION_URL)

    assert api.requests == []


def test_local_mode_cannot_build_a_client_without_a_mock_transport():
    with pytest.raises(AssertionError, match="never touch the network"):
        common.build_client(LOCAL_URL)
