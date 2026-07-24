"""
Non-PostgreSQL tests for the audit-permission verifier.

These need no database: they cover the guard that refuses SQLite and the shape of
the required-privilege matrix. The effective-privilege checks themselves are
PostgreSQL-only and live in tests/test_audit_permissions_postgres.py.
"""

import pytest

from scripts.verify_audit_permissions import (
    REQUIRED_PRIVILEGES,
    _reject_non_postgres,
)


def test_rejects_sqlite():
    with pytest.raises(SystemExit, match="PostgreSQL-only"):
        _reject_non_postgres("sqlite:///./test.db")


def test_rejects_non_postgres_backend():
    with pytest.raises(SystemExit):
        _reject_non_postgres("mysql://user:pw@localhost/db")


def test_accepts_a_postgres_url():
    # URL parsing only — no connection is made.
    _reject_non_postgres("postgresql://user:pw@localhost:5432/evoting")


def test_required_tables_are_schema_qualified():
    """Every checked table is named public.* so search_path cannot mislead it."""
    assert set(REQUIRED_PRIVILEGES) == {"public.audit_logs", "public.audit_chain_head"}


def test_required_matrix_encodes_the_append_only_policy():
    audit_logs = REQUIRED_PRIVILEGES["public.audit_logs"]
    assert audit_logs["INSERT"] is True
    assert audit_logs["SELECT"] is True
    # The tamper privileges must be required-denied.
    assert audit_logs["UPDATE"] is False
    assert audit_logs["DELETE"] is False
    assert audit_logs["TRUNCATE"] is False

    head = REQUIRED_PRIVILEGES["public.audit_chain_head"]
    # The head is rewritten on every append.
    assert head["UPDATE"] is True
    assert head["SELECT"] is True
    assert head["INSERT"] is True
    assert head["DELETE"] is False
    assert head["TRUNCATE"] is False
