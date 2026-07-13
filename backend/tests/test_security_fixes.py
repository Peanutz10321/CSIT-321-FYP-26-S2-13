"""
Tests for the Day-2/3 secrecy fixes (security-fixes branch).

Pins three properties:
1. vote_hash no longer encodes the candidate choice — a DB reader cannot
   brute-force the old sha256(election:voter:candidate:time) formula.
2. Ciphertexts are freshly obfuscated — two encryptions of the same value
   are never byte-identical, so stored E(0)/E(1) can't be pattern-matched.
3. The receipt exposes the plaintext choice ONLY in the immediate submit
   response, never when fetching the stored ballot later.
"""

import hashlib
import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from phe import paillier
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.ballot import Ballot, BulletinStatus
from app.models.election import Election
from app.models.election_key import ElectionKey
from app.models.election_voter import ElectionVoter
from app.security.homomorphic import _enc_to_dict, encrypt_vote
from app.security.keystore import ElectionKeyMissingError, load_private_key


client = TestClient(app)

AUTH_BASE = "/auth"
ELECTION_BASE = "/elections"
VOTE_BASE = "/votes"


def unique_text(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_user(role: str) -> dict:
    suffix = uuid4().hex[:8]

    payload = {
        "role": role,
        "external_id": f"INST-{suffix}",
        "username": f"{role}_{suffix}",
        "full_name": f"Test {role.title()}",
        "email": f"{role}_{suffix}@test.com",
        "password": "testing123",
    }

    response = client.post(f"{AUTH_BASE}/register", json=payload)
    assert response.status_code in [200, 201], response.text

    return {**payload, **response.json()}


def login_user(email: str, password: str = "testing123") -> str:
    response = client.post(
        f"{AUTH_BASE}/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def organizer_token():
    organizer = register_user("organizer")
    return login_user(organizer["email"])


@pytest.fixture
def voter_user():
    return register_user("voter")


@pytest.fixture
def voter_token(voter_user):
    return login_user(voter_user["email"])


def valid_election_payload() -> dict:
    now = datetime.utcnow()

    return {
        "title": unique_text("Security Fixes Election"),
        "description": "Election for security regression tests",
        "start_date": (now - timedelta(minutes=10)).isoformat(),
        "end_date": (now + timedelta(hours=24)).isoformat(),
        "candidates": [
            {
                "name": unique_text("Alice"),
                "description": "Candidate A",
                "photo_url": None,
                "display_order": 1,
            },
            {
                "name": unique_text("Bob"),
                "description": "Candidate B",
                "photo_url": None,
                "display_order": 2,
            },
        ],
    }


def prepare_active_election_with_voter(organizer_token: str, voter_user: dict) -> dict:
    response = client.post(
        f"{ELECTION_BASE}/draft",
        json=valid_election_payload(),
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 201, response.text
    election = response.json()

    response = client.post(
        f"{ELECTION_BASE}/{election['id']}/voters",
        json={"external_id": voter_user["external_id"]},
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 201, response.text

    response = client.patch(
        f"{ELECTION_BASE}/{election['id']}/activate",
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 200, response.text

    return election


def cast_vote(voter_token: str, election: dict, candidate_index: int = 0) -> dict:
    response = client.post(
        VOTE_BASE,
        json={
            "election_id": election["id"],
            "candidate_id": election["candidates"][candidate_index]["id"],
        },
        headers=auth_header(voter_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 1. vote_hash must not encode the recoverable choice
# ---------------------------------------------------------------------------

class TestVoteHashSecrecy:
    def test_hash_not_brute_forceable_from_db_row(
        self, organizer_token, voter_user, voter_token
    ):
        """An attacker with the ballot row + voter identity must not be able
        to recover the choice by hashing every candidate (the old formula)."""
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        vote = cast_vote(voter_token, election)

        db = SessionLocal()
        try:
            ballot = db.query(Ballot).filter(Ballot.id == UUID(vote["id"])).first()
            assert ballot is not None
            voter_id = voter_user["id"]

            for candidate in election["candidates"]:
                old_formula = hashlib.sha256(
                    f"{election['id']}:{voter_id}:{candidate['id']}:{ballot.submitted_at.isoformat()}".encode()
                ).hexdigest()
                assert ballot.vote_hash != old_formula
        finally:
            db.close()

    def test_hash_does_not_contain_candidate_id(
        self, organizer_token, voter_user, voter_token
    ):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        vote = cast_vote(voter_token, election)

        for candidate in election["candidates"]:
            assert candidate["id"] not in vote["vote_hash"]


# ---------------------------------------------------------------------------
# 2. Ciphertext obfuscation — no pattern-matching stored votes
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fast_pk():
    pk, _ = paillier.generate_paillier_keypair(n_length=1024)
    return pk


class TestCiphertextObfuscation:
    def test_two_encryptions_of_zero_are_not_identical(self, fast_pk):
        first = _enc_to_dict(fast_pk.encrypt(0))
        second = _enc_to_dict(fast_pk.encrypt(0))
        assert first["c"] != second["c"]

    def test_two_identical_votes_produce_different_ciphertexts(self, fast_pk):
        ids = [str(uuid4()) for _ in range(3)]
        first = json.loads(encrypt_vote(fast_pk, ids, ids[0]))
        second = json.loads(encrypt_vote(fast_pk, ids, ids[0]))

        for cid in ids:
            assert first[cid]["c"] != second[cid]["c"]


# ---------------------------------------------------------------------------
# 3. Receipt: choice visible at submission only, never afterwards
# ---------------------------------------------------------------------------

class TestReceiptSecrecy:
    def test_submit_response_names_the_chosen_candidate(
        self, organizer_token, voter_user, voter_token
    ):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        vote = cast_vote(voter_token, election, candidate_index=1)

        assert vote["candidate_name"] == election["candidates"][1]["name"]

    def test_stored_ballot_never_reveals_candidate_name(
        self, organizer_token, voter_user, voter_token
    ):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        vote = cast_vote(voter_token, election)

        response = client.get(
            f"{VOTE_BASE}/{vote['id']}",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["candidate_name"] is None


# ---------------------------------------------------------------------------
# 4. Keystore: private key out of the elections table, encrypted at rest
# ---------------------------------------------------------------------------

class TestKeystore:
    def test_elections_table_holds_no_private_key(
        self, organizer_token, voter_user
    ):
        election = prepare_active_election_with_voter(organizer_token, voter_user)

        assert not hasattr(Election, "private_key_json")

        db = SessionLocal()
        try:
            key_row = db.get(ElectionKey, UUID(election["id"]))
            assert key_row is not None
            # Fernet token, not plaintext {"p": ..., "q": ...} JSON
            assert '"p"' not in key_row.encrypted_private_key
            assert key_row.encrypted_private_key.startswith("gAAAA")
        finally:
            db.close()

    def test_stored_key_round_trips_through_keystore(
        self, organizer_token, voter_user
    ):
        election = prepare_active_election_with_voter(organizer_token, voter_user)

        db = SessionLocal()
        try:
            row = db.query(Election).filter(Election.id == UUID(election["id"])).first()
            private_key = load_private_key(db, row)
            public_key = private_key.public_key
            assert private_key.decrypt(public_key.encrypt(7)) == 7
        finally:
            db.close()

    def test_missing_key_raises(self):
        db = SessionLocal()
        try:
            orphan = Election(id=uuid4())
            with pytest.raises(ElectionKeyMissingError):
                load_private_key(db, orphan)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 5. Audit log: security-relevant events leave an append-only trail
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_casting_a_vote_writes_an_audit_row_without_the_choice(
        self, organizer_token, voter_user, voter_token
    ):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        cast_vote(voter_token, election)

        db = SessionLocal()
        try:
            row = (
                db.query(AuditLog)
                .filter(
                    AuditLog.actor_user_id == UUID(voter_user["id"]),
                    AuditLog.action == "vote_cast",
                )
                .first()
            )
            assert row is not None
            assert row.entity_type == "ballot"
            # The audit trail records THAT a vote happened, never the choice
            for candidate in election["candidates"]:
                assert candidate["id"] not in (row.details or "")
        finally:
            db.close()

    def test_activation_logs_key_generated(self, organizer_token, voter_user):
        election = prepare_active_election_with_voter(organizer_token, voter_user)

        db = SessionLocal()
        try:
            actions = {
                row.action
                for row in db.query(AuditLog)
                .filter(AuditLog.entity_id == UUID(election["id"]))
                .all()
            }
            assert "key_generated" in actions
            assert "election_activated" in actions
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 6. Double-vote protection: the DB constraint behind the 400 error path
# ---------------------------------------------------------------------------

class TestDoubleVoteConstraint:
    def test_second_ballot_for_same_election_voter_violates_constraint(
        self, organizer_token, voter_user, voter_token
    ):
        """The route's IntegrityError -> 400 handling relies on the unique
        constraint on ballot.election_voter_id; pin that it actually fires."""
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        cast_vote(voter_token, election)

        db = SessionLocal()
        try:
            election_voter = (
                db.query(ElectionVoter)
                .filter(
                    ElectionVoter.election_id == UUID(election["id"]),
                    ElectionVoter.voter_id == UUID(voter_user["id"]),
                )
                .first()
            )
            assert election_voter is not None

            duplicate = Ballot(
                election_id=UUID(election["id"]),
                election_voter_id=election_voter.id,
                encrypted_vote="{}",
                vote_hash=uuid4().hex,
                receipt_code=f"RCPT-{uuid4().hex[:12].upper()}",
                submitted_at=datetime.utcnow(),
                bulletin_status=BulletinStatus.published,
            )
            db.add(duplicate)

            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
        finally:
            db.close()
