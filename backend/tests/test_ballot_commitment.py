"""
Unit tests for the ballot commitment.

These cover the properties the commitment is claimed to have: it is deterministic,
it is keyed, it changes when any covered field changes, and it never carries a
plaintext choice. The endpoint-level behaviour is covered in test_votes.py.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.security.ballot_commitment import (
    COMMITMENT_SCHEME_VERSION,
    ballot_configuration_digest,
    build_commitment_input,
    commitment_matches,
    compute_ballot_commitment,
)


SUBMITTED_AT = datetime(2026, 3, 1, 12, 30, 0)


def _inputs(**overrides):
    base = {
        "ballot_id": uuid4(),
        "election_id": uuid4(),
        "receipt_code": "RCPT-ABC123DEF456",
        "encrypted_vote": '{"a":{"c":"12345","e":0}}',
        "ballot_config_digest": ballot_configuration_digest("single", 1, [uuid4()]),
        "submitted_at": SUBMITTED_AT,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Determinism and keying
# ---------------------------------------------------------------------------


def test_same_input_always_produces_the_same_commitment():
    inputs = _inputs()
    assert compute_ballot_commitment(**inputs) == compute_ballot_commitment(**inputs)


def test_commitment_is_hex_sha256_length():
    assert len(compute_ballot_commitment(**_inputs())) == 64


def test_commitment_depends_on_the_signing_secret(monkeypatch):
    """Without the key the commitment cannot be reproduced."""
    from app.config import settings

    inputs = _inputs()
    original = compute_ballot_commitment(**inputs)

    monkeypatch.setattr(settings, "RECEIPT_SIGNING_SECRET", "a-different-secret")
    assert compute_ballot_commitment(**inputs) != original


def test_canonical_input_is_order_independent():
    """Field ordering must not change the serialisation."""
    inputs = _inputs()
    forward = build_commitment_input(**inputs)
    shuffled = dict(reversed(list(forward.items())))
    assert forward == shuffled


def test_scheme_version_is_part_of_the_committed_input():
    assert build_commitment_input(**_inputs())["v"] == COMMITMENT_SCHEME_VERSION


# ---------------------------------------------------------------------------
# Every covered field must change the commitment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("ballot_id", uuid4()),
        ("election_id", uuid4()),
        ("receipt_code", "RCPT-TAMPERED0001"),
        ("encrypted_vote", '{"a":{"c":"99999","e":0}}'),
        ("ballot_config_digest", ballot_configuration_digest("multi", 2, [uuid4()])),
        ("submitted_at", SUBMITTED_AT + timedelta(seconds=1)),
    ],
)
def test_changing_any_committed_field_changes_the_commitment(field, replacement):
    """This is the whole point: tampering with a stored ballot must be detectable."""
    baseline = compute_ballot_commitment(**_inputs())
    tampered = compute_ballot_commitment(**_inputs(**{field: replacement}))

    assert tampered != baseline


def test_swapping_the_ciphertext_between_two_ballots_is_detected():
    """Pasting one voter's ciphertext onto another's ballot row must not verify."""
    first = _inputs(encrypted_vote='{"a":{"c":"11111","e":0}}')
    second = _inputs(encrypted_vote='{"a":{"c":"22222","e":0}}')

    assert first["encrypted_vote"] != second["encrypted_vote"]

    original = compute_ballot_commitment(**first)
    swapped = dict(first, encrypted_vote=second["encrypted_vote"])

    assert compute_ballot_commitment(**swapped) != original


# ---------------------------------------------------------------------------
# Ballot configuration digest
# ---------------------------------------------------------------------------


def test_configuration_digest_ignores_candidate_ordering():
    ids = [uuid4() for _ in range(3)]

    assert ballot_configuration_digest("single", 1, ids) == ballot_configuration_digest(
        "single", 1, list(reversed(ids))
    )


def test_configuration_digest_detects_an_added_candidate():
    ids = [uuid4() for _ in range(3)]

    assert ballot_configuration_digest("single", 1, ids) != ballot_configuration_digest(
        "single", 1, ids + [uuid4()]
    )


def test_configuration_digest_detects_a_swapped_candidate():
    ids = [uuid4() for _ in range(3)]
    swapped = ids[:-1] + [uuid4()]

    assert ballot_configuration_digest("single", 1, ids) != ballot_configuration_digest(
        "single", 1, swapped
    )


def test_configuration_digest_detects_ballot_type_and_limit_changes():
    ids = [uuid4() for _ in range(3)]
    baseline = ballot_configuration_digest("single", 1, ids)

    assert ballot_configuration_digest("multi", 1, ids) != baseline
    assert ballot_configuration_digest("single", 2, ids) != baseline


def test_configuration_digest_carries_no_plaintext_candidate_id():
    """Candidate ids must not appear outside the encrypted ballot."""
    ids = [uuid4() for _ in range(3)]
    digest = ballot_configuration_digest("single", 1, ids)

    for candidate_id in ids:
        assert str(candidate_id) not in digest


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def test_commitment_matches_accepts_the_correct_value():
    commitment = compute_ballot_commitment(**_inputs())
    assert commitment_matches(commitment, commitment)


def test_commitment_matches_rejects_a_different_value():
    assert not commitment_matches(compute_ballot_commitment(**_inputs()), "0" * 64)


@pytest.mark.parametrize("stored", [None, ""])
def test_commitment_matches_rejects_a_missing_stored_value(stored):
    """A legacy ballot with no usable commitment must never verify."""
    assert not commitment_matches(compute_ballot_commitment(**_inputs()), stored)
