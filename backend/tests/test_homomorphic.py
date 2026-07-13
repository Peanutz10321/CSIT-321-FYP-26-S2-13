"""
Tests for Paillier homomorphic encryption (app/security/homomorphic.py).

Unit tests use 1024-bit keys via a module-scoped fixture so the suite runs
quickly — key generation happens once per module, not once per test.

Integration tests (TestHEIntegration) call the real activate endpoint, which
generates full 2048-bit keys; they are intentionally slower.
"""

import json
import random
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from phe import paillier
from phe.paillier import EncryptedNumber

from app.database import SessionLocal
from app.main import app
from app.models.election import Election
from app.security.homomorphic import (
    deserialize_private_key,
    deserialize_public_key,
    encrypt_ballot,
    encrypt_vote,
    generate_keypair,
    homomorphic_tally,
    serialize_private_key,
    serialize_public_key,
)

# ---------------------------------------------------------------------------
# Shared fast keypair — 1024-bit, generated once for all unit tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def keypair():
    pk, sk = paillier.generate_paillier_keypair(n_length=1024)
    return pk, sk


@pytest.fixture(scope="module")
def pk(keypair):
    return keypair[0]


@pytest.fixture(scope="module")
def sk(keypair):
    return keypair[1]


def candidate_ids(n: int = 3) -> list[str]:
    return [str(uuid4()) for _ in range(n)]


# ---------------------------------------------------------------------------
# Key generation and serialization
# ---------------------------------------------------------------------------

class TestKeyPair:
    def test_generate_keypair_produces_working_pair(self):
        public_key, private_key = generate_keypair()
        assert private_key.decrypt(public_key.encrypt(42)) == 42

    def test_public_key_serializes_as_integer_string(self, pk):
        s = serialize_public_key(pk)
        assert isinstance(s, str)
        int(s)  # must parse as integer

    def test_public_key_round_trips(self, pk):
        restored = deserialize_public_key(serialize_public_key(pk))
        assert restored.n == pk.n

    def test_private_key_serializes_as_json_with_p_and_q(self, pk, sk):
        data = json.loads(serialize_private_key(sk))
        assert "p" in data and "q" in data

    def test_private_key_round_trips(self, pk, sk):
        restored = deserialize_private_key(serialize_private_key(sk), pk)
        assert restored.decrypt(pk.encrypt(123)) == 123

    def test_deserializing_with_wrong_key_size_raises(self, pk, sk):
        other_pk, _ = paillier.generate_paillier_keypair(n_length=1024)
        serialized = serialize_private_key(sk)
        # phe validates p*q == n at construction time, so mismatch raises here
        with pytest.raises(Exception):
            deserialize_private_key(serialized, other_pk)


# ---------------------------------------------------------------------------
# Vote encryption
# ---------------------------------------------------------------------------

class TestVoteEncrypt:
    def test_output_is_valid_json(self, pk):
        ids = candidate_ids()
        result = encrypt_vote(pk, ids, ids[0])
        json.loads(result)  # must not raise

    def test_output_contains_all_candidates(self, pk):
        ids = candidate_ids(4)
        parsed = json.loads(encrypt_vote(pk, ids, ids[2]))
        assert set(parsed.keys()) == set(ids)

    def test_each_entry_has_ciphertext_and_exponent(self, pk):
        ids = candidate_ids(2)
        parsed = json.loads(encrypt_vote(pk, ids, ids[0]))
        for entry in parsed.values():
            assert "c" in entry and "e" in entry

    def test_chosen_candidate_decrypts_to_one(self, pk, sk):
        ids = candidate_ids(3)
        voted = ids[1]
        parsed = json.loads(encrypt_vote(pk, ids, voted))
        for cid, data in parsed.items():
            enc = EncryptedNumber(pk, int(data["c"]), data["e"])
            assert sk.decrypt(enc) == (1 if cid == voted else 0)

    def test_all_others_decrypt_to_zero(self, pk, sk):
        ids = candidate_ids(5)
        voted = ids[3]
        parsed = json.loads(encrypt_vote(pk, ids, voted))
        non_voted = [cid for cid in ids if cid != voted]
        for cid in non_voted:
            enc = EncryptedNumber(pk, int(parsed[cid]["c"]), parsed[cid]["e"])
            assert sk.decrypt(enc) == 0

    def test_same_vote_produces_different_ciphertexts(self, pk):
        """Paillier is semantically secure: same plaintext → different ciphertext each time."""
        ids = candidate_ids(2)
        enc1 = json.loads(encrypt_vote(pk, ids, ids[0]))
        enc2 = json.loads(encrypt_vote(pk, ids, ids[0]))
        assert enc1[ids[0]]["c"] != enc2[ids[0]]["c"]

    def test_ciphertext_does_not_structurally_reveal_choice(self, pk):
        """Both votes have the same number of entries regardless of which candidate was chosen."""
        ids = candidate_ids(4)
        for voted in ids:
            parsed = json.loads(encrypt_vote(pk, ids, voted))
            assert set(parsed.keys()) == set(ids)


# ---------------------------------------------------------------------------
# Multi-select / abstention ballot encryption
# ---------------------------------------------------------------------------

class TestBallotEncrypt:
    def test_multi_hot_vector_decrypts_to_selected_ones(self, pk, sk):
        ids = candidate_ids(4)
        selected = [ids[0], ids[2]]
        parsed = json.loads(encrypt_ballot(pk, ids, selected))
        assert set(parsed.keys()) == set(ids)
        for cid, data in parsed.items():
            enc = EncryptedNumber(pk, int(data["c"]), data["e"])
            assert sk.decrypt(enc) == (1 if cid in selected else 0)

    def test_single_selection_matches_one_hot(self, pk, sk):
        ids = candidate_ids(3)
        parsed = json.loads(encrypt_ballot(pk, ids, [ids[1]]))
        for cid, data in parsed.items():
            enc = EncryptedNumber(pk, int(data["c"]), data["e"])
            assert sk.decrypt(enc) == (1 if cid == ids[1] else 0)

    def test_abstention_is_encrypted_all_zero_vector(self, pk, sk):
        ids = candidate_ids(3)
        parsed = json.loads(encrypt_ballot(pk, ids, []))
        assert set(parsed.keys()) == set(ids)
        for data in parsed.values():
            # Genuinely encrypted zero, not a plaintext "0" placeholder.
            assert data["c"] != "0"
            assert len(data["c"]) > 10
            enc = EncryptedNumber(pk, int(data["c"]), data["e"])
            assert sk.decrypt(enc) == 0

    def test_two_abstentions_produce_different_ciphertexts(self, pk):
        """Semantic security: two encrypted-zero abstentions must not be byte-identical."""
        ids = candidate_ids(2)
        first = json.loads(encrypt_ballot(pk, ids, []))
        second = json.loads(encrypt_ballot(pk, ids, []))
        for cid in ids:
            assert first[cid]["c"] != second[cid]["c"]

    def test_tally_counts_multi_hot_and_ignores_abstention(self, pk, sk):
        ids = candidate_ids(3)
        ballots = [
            encrypt_ballot(pk, ids, [ids[0], ids[1]]),  # A, B
            encrypt_ballot(pk, ids, [ids[0]]),          # A
            encrypt_ballot(pk, ids, []),                # abstention
        ]
        result = homomorphic_tally(pk, sk, ballots, ids)
        assert result == {ids[0]: 2, ids[1]: 1, ids[2]: 0}


# ---------------------------------------------------------------------------
# Homomorphic tally
# ---------------------------------------------------------------------------

class TestHomomorphicTally:
    def test_single_vote_counted_correctly(self, pk, sk):
        ids = candidate_ids(3)
        result = homomorphic_tally(pk, sk, [encrypt_vote(pk, ids, ids[0])], ids)
        assert result == {ids[0]: 1, ids[1]: 0, ids[2]: 0}

    def test_multiple_votes_summed_correctly(self, pk, sk):
        ids = candidate_ids(3)
        votes = [
            encrypt_vote(pk, ids, ids[0]),
            encrypt_vote(pk, ids, ids[0]),
            encrypt_vote(pk, ids, ids[1]),
        ]
        result = homomorphic_tally(pk, sk, votes, ids)
        assert result == {ids[0]: 2, ids[1]: 1, ids[2]: 0}

    def test_empty_ballot_box_returns_zeros(self, pk, sk):
        ids = candidate_ids(2)
        result = homomorphic_tally(pk, sk, [], ids)
        assert result == {ids[0]: 0, ids[1]: 0}

    def test_tally_sum_equals_total_ballots_cast(self, pk, sk):
        ids = candidate_ids(4)
        n = 10
        votes = [encrypt_vote(pk, ids, random.choice(ids)) for _ in range(n)]
        result = homomorphic_tally(pk, sk, votes, ids)
        assert sum(result.values()) == n

    def test_result_contains_all_candidates(self, pk, sk):
        ids = candidate_ids(5)
        result = homomorphic_tally(pk, sk, [], ids)
        assert set(result.keys()) == set(ids)

    def test_result_values_are_integers(self, pk, sk):
        """The tally returns plain integers — no ciphertext objects leak out."""
        ids = candidate_ids(3)
        votes = [encrypt_vote(pk, ids, ids[0])]
        result = homomorphic_tally(pk, sk, votes, ids)
        for v in result.values():
            assert isinstance(v, int)

    def test_all_votes_for_one_candidate(self, pk, sk):
        ids = candidate_ids(3)
        n = 7
        votes = [encrypt_vote(pk, ids, ids[2]) for _ in range(n)]
        result = homomorphic_tally(pk, sk, votes, ids)
        assert result[ids[2]] == n
        assert result[ids[0]] == 0
        assert result[ids[1]] == 0

    def test_tally_is_consistent_across_different_key_deserialisations(self, pk, sk):
        """Keys deserialized from storage should produce the same tally."""
        ids = candidate_ids(2)
        votes = [encrypt_vote(pk, ids, ids[0]), encrypt_vote(pk, ids, ids[1])]

        pk2 = deserialize_public_key(serialize_public_key(pk))
        sk2 = deserialize_private_key(serialize_private_key(sk), pk2)

        result = homomorphic_tally(pk2, sk2, votes, ids)
        assert result == {ids[0]: 1, ids[1]: 1}


# ---------------------------------------------------------------------------
# API integration tests (2048-bit keys, slower)
# ---------------------------------------------------------------------------

client = TestClient(app)

AUTH_BASE = "/auth"
ELECTION_BASE = "/elections"
VOTE_BASE = "/votes"
RESULT_BASE = "/results"


def _register(role: str) -> dict:
    suffix = uuid4().hex[:8]
    payload = {
        "role": role,
        "external_id": f"INST-{suffix}",
        "username": f"{role}_{suffix}",
        "full_name": f"Test {role.title()}",
        "email": f"{role}_{suffix}@test.com",
        "password": "testing123",
    }
    r = client.post(f"{AUTH_BASE}/register", json=payload)
    assert r.status_code in [200, 201], r.text
    return {**payload, **r.json()}


def _login(email: str, password: str = "testing123") -> str:
    r = client.post(f"{AUTH_BASE}/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _election_payload() -> dict:
    now = datetime.utcnow()
    return {
        "title": f"Election_{uuid4().hex[:8]}",
        "description": "Test election",
        "start_date": (now - timedelta(minutes=10)).isoformat(),
        "end_date": (now + timedelta(hours=24)).isoformat(),
        "candidates": [
            {"name": f"Alice_{uuid4().hex[:6]}", "description": "A", "photo_url": None, "display_order": 1},
            {"name": f"Bob_{uuid4().hex[:6]}", "description": "B", "photo_url": None, "display_order": 2},
        ],
    }


class TestHEIntegration:
    """
    End-to-end tests for the Paillier-encrypted vote flow through the API.
    Each test activates an election via the real endpoint, which generates
    a full 2048-bit keypair — these tests are intentionally slower.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        organizer = _register("organizer")
        voter = _register("voter")
        self.organizer_token = _login(organizer["email"])
        self.voter_token = _login(voter["email"])
        self.voter = voter

    def _create_and_activate(self) -> dict:
        r = client.post(f"{ELECTION_BASE}/draft", json=_election_payload(), headers=_auth(self.organizer_token))
        assert r.status_code == 201, r.text
        election = r.json()

        r = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": self.voter["external_id"]},
            headers=_auth(self.organizer_token),
        )
        assert r.status_code == 201, r.text

        # Activate generates the Paillier keypair
        r = client.patch(
            f"{ELECTION_BASE}/{election['id']}/activate",
            headers=_auth(self.organizer_token),
        )
        assert r.status_code == 200, r.text

        return election

    def test_encrypted_vote_is_he_json_not_placeholder(self):
        election = self._create_and_activate()
        candidate_id = election["candidates"][0]["id"]

        r = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=_auth(self.voter_token),
        )

        assert r.status_code == 201, r.text
        encrypted_vote = r.json()["encrypted_vote"]

        assert not encrypted_vote.startswith("encrypted_placeholder"), (
            "Vote must be a Paillier ciphertext, not the legacy placeholder"
        )

        parsed = json.loads(encrypted_vote)
        candidate_ids_in_election = {c["id"] for c in election["candidates"]}
        assert set(parsed.keys()) == candidate_ids_in_election

    def test_each_slot_has_ciphertext_fields(self):
        election = self._create_and_activate()
        candidate_id = election["candidates"][0]["id"]

        r = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=_auth(self.voter_token),
        )

        assert r.status_code == 201, r.text
        parsed = json.loads(r.json()["encrypted_vote"])

        for entry in parsed.values():
            assert "c" in entry and "e" in entry

    def test_he_tally_returns_correct_vote_count(self):
        election = self._create_and_activate()
        candidate_id = election["candidates"][0]["id"]

        client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=_auth(self.voter_token),
        )

        # The tally now runs at close time, not on read.
        close = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=_auth(self.organizer_token),
        )
        assert close.status_code == 200, close.text

        r = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=_auth(self.organizer_token),
        )

        assert r.status_code == 200, r.text
        results = {item["candidate_id"]: item["total_votes"] for item in r.json()["results"]}
        assert results[candidate_id] == 1
        assert results[election["candidates"][1]["id"]] == 0

    def test_cannot_vote_in_election_without_keys(self):
        """An election force-set to active without going through the activate
        endpoint has no keys — voting must return 500."""
        from app.models.election import ElectionStatus as ES

        # Create as a draft so no keypair is generated, then force-activate below.
        r = client.post(f"{ELECTION_BASE}/draft", json=_election_payload(), headers=_auth(self.organizer_token))
        assert r.status_code == 201
        election = r.json()

        r = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": self.voter["external_id"]},
            headers=_auth(self.organizer_token),
        )
        assert r.status_code == 201

        # Bypass the activate endpoint — keys are never generated
        db = SessionLocal()
        try:
            e = db.query(Election).filter(Election.id == UUID(election["id"])).first()
            e.status = ES.active
            db.commit()
        finally:
            db.close()

        r = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": election["candidates"][0]["id"]},
            headers=_auth(self.voter_token),
        )

        assert r.status_code == 500
        assert "keys" in r.json()["detail"].lower()
