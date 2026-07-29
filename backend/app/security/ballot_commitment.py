"""
Ballot commitment.

The receipt a voter receives must commit to the *actual encrypted ballot*, not
merely prove that some row exists. The commitment is an HMAC-SHA256 over a
canonical serialisation of the ballot's identifying fields and its complete
ciphertext, keyed with RECEIPT_SIGNING_SECRET.

One function is used everywhere a commitment is produced — the vote route, the
demo seed, and the tests — so the value can never be computed two different ways.

What this guarantees
--------------------
Changing any committed field (the ciphertext, receipt code, election, ballot id,
submission time, or the ballot configuration) would invalidate the commitment,
so a stored commitment is capable of detecting modification made through
database access alone, and accidental corruption.

Not currently verified
----------------------
Commitments are generated and stored, and returned on the receipt, but nothing
in the running application recomputes or compares them: there is no verification
endpoint, no frontend check, and the tally does not validate ballots against
their commitments before publishing results. The stored value is evidence that
can be checked out of band; it is not an active tamper-detection control.
Verification is deferred future work.

What this does NOT guarantee
----------------------------
This is not end-to-end verifiability. The backend holds the signing secret, so a
compromised backend — or anyone who obtains that secret — can mint a commitment
for a ballot it substitutes. The voter cannot independently verify their vote was
counted as cast; they could only detect tampering by a party lacking the key.
Plaintext choices are never part of the commitment input.
"""

import hashlib
import hmac
import json
from datetime import datetime
from uuid import UUID

from app.config import settings


# Bumping this changes every commitment. It exists so a future change to the
# canonical form is an explicit, detectable migration rather than silent drift.
COMMITMENT_SCHEME_VERSION = 1


def _canonical_json(payload: dict) -> bytes:
    """Deterministic serialisation: identical input always yields identical bytes."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def ballot_configuration_digest(
    ballot_type: str,
    max_selections: int,
    candidate_ids: list[str] | list[UUID],
) -> str:
    """Digest binding the ballot configuration and candidate set.

    A digest rather than the raw identifiers: the commitment must not carry
    plaintext candidate ids outside the encrypted ballot, but it still has to
    detect a candidate being added, removed, or swapped after the fact.
    """
    ordered = sorted(str(candidate_id) for candidate_id in candidate_ids)

    return hashlib.sha256(
        _canonical_json(
            {
                "ballot_type": str(ballot_type),
                "max_selections": int(max_selections),
                "candidate_ids": ordered,
            }
        )
    ).hexdigest()


def build_commitment_input(
    *,
    ballot_id: UUID | str,
    election_id: UUID | str,
    receipt_code: str,
    encrypted_vote: str,
    ballot_config_digest: str,
    submitted_at: datetime,
) -> dict:
    """The exact set of fields the commitment covers."""
    return {
        "v": COMMITMENT_SCHEME_VERSION,
        "ballot_id": str(ballot_id),
        "election_id": str(election_id),
        "receipt_code": receipt_code,
        "encrypted_vote": encrypted_vote,
        "ballot_config": ballot_config_digest,
        "submitted_at": submitted_at.isoformat(),
    }


def compute_ballot_commitment(
    *,
    ballot_id: UUID | str,
    election_id: UUID | str,
    receipt_code: str,
    encrypted_vote: str,
    ballot_config_digest: str,
    submitted_at: datetime,
) -> str:
    """HMAC-SHA256 commitment over the canonical ballot input."""
    message = _canonical_json(
        build_commitment_input(
            ballot_id=ballot_id,
            election_id=election_id,
            receipt_code=receipt_code,
            encrypted_vote=encrypted_vote,
            ballot_config_digest=ballot_config_digest,
            submitted_at=submitted_at,
        )
    )

    return hmac.new(
        settings.RECEIPT_SIGNING_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
