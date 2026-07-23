"""Unit tests for the demo-seed fail-closed guard."""

import pytest

from scripts.demo_seed_guard import (
    require_demo_password,
    require_reset_confirmation,
    require_safe_demo_database,
)


SAFE_URL = "postgresql://user:pw@localhost:5432/evoting_demo"


def _check(db_url=SAFE_URL, seed_allowed="true", hosts="localhost", databases="evoting_demo"):
    require_safe_demo_database(
        db_url,
        seed_allowed=seed_allowed,
        allowed_hosts=hosts,
        allowed_databases=databases,
    )


def test_allows_a_fully_allowlisted_target():
    _check()  # must not raise


def test_allowlists_are_case_insensitive_and_accept_multiple_entries():
    _check(hosts="Localhost, db.internal", databases="other_db, EVOTING_DEMO")


def test_rejects_missing_database_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        _check(db_url=None)


@pytest.mark.parametrize("value", [None, "", "false", "1", "yes", "TRUE_ISH"])
def test_rejects_without_explicit_opt_in(value):
    """Only the exact string 'true' arms the script."""
    with pytest.raises(RuntimeError, match="DEMO_SEED_ALLOWED=true"):
        _check(seed_allowed=value)


def test_accepts_opt_in_case_insensitively():
    _check(seed_allowed="TRUE")


def test_rejects_when_host_allowlist_is_unset():
    """An unset allowlist must refuse, never wave the run through."""
    with pytest.raises(RuntimeError, match="DEMO_SEED_ALLOWED_HOSTS"):
        _check(hosts=None)


def test_rejects_when_database_allowlist_is_unset():
    with pytest.raises(RuntimeError, match="DEMO_SEED_ALLOWED_DATABASES"):
        _check(databases=None)


def test_rejects_host_outside_the_allowlist():
    with pytest.raises(RuntimeError, match="host"):
        _check(db_url="postgresql://user:pw@db.example.supabase.co:5432/evoting_demo")


def test_rejects_database_outside_the_allowlist():
    with pytest.raises(RuntimeError, match="database"):
        _check(db_url="postgresql://user:pw@localhost:5432/production")


def test_rejection_message_does_not_echo_the_target_host():
    """A misconfigured run must not print part of a connection string."""
    with pytest.raises(RuntimeError) as error:
        _check(db_url="postgresql://user:pw@secret-host.example.com:5432/evoting_demo")

    assert "secret-host" not in str(error.value)


def test_reset_is_required_before_truncating():
    with pytest.raises(RuntimeError, match="--reset"):
        require_reset_confirmation(False)


def test_reset_confirmation_passes_when_requested():
    require_reset_confirmation(True)  # must not raise


def test_password_must_be_provided():
    with pytest.raises(RuntimeError, match="DEMO_SEED_PASSWORD"):
        require_demo_password(None)


def test_password_must_not_be_empty():
    with pytest.raises(RuntimeError, match="DEMO_SEED_PASSWORD"):
        require_demo_password("")


def test_password_must_meet_minimum_length():
    with pytest.raises(RuntimeError, match="8 characters"):
        require_demo_password("short")


def test_password_is_returned_when_valid():
    assert require_demo_password("longenough123") == "longenough123"
