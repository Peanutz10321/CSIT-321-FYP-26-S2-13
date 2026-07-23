from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from tests.factories import provision_from_payload
from app.models.election import Election, ElectionStatus


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

    # Public registration creates voters only; organizers are provisioned by an
    # admin, so tests that merely need one insert it directly.
    if role != "voter":
        return {**payload, **provision_from_payload(payload)}

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


@pytest.fixture
def other_voter_token():
    voter = register_user("voter")
    return login_user(voter["email"])


def valid_election_payload() -> dict:
    now = datetime.utcnow()

    return {
        "title": unique_text("Class Representative Election"),
        "description": "Election for class representative",
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


def create_election_as_organizer(organizer_token: str) -> dict:
    response = client.post(
        f"{ELECTION_BASE}/draft",
        json=valid_election_payload(),
        headers=auth_header(organizer_token),
    )

    assert response.status_code == 201, response.text
    return response.json()


def set_election_status(election_id: str, status: ElectionStatus):
    db = SessionLocal()
    try:
        election = db.query(Election).filter(Election.id == UUID(election_id)).first()
        assert election is not None
        election.status = status
        db.commit()
    finally:
        db.close()


def add_voter_to_election(organizer_token: str, election_id: str, voter_user: dict):
    response = client.post(
        f"{ELECTION_BASE}/{election_id}/voters",
        json={"external_id": voter_user["external_id"]},
        headers=auth_header(organizer_token),
    )

    assert response.status_code == 201, response.text
    return response.json()


def activate_election(organizer_token: str, election_id: str):
    response = client.patch(
        f"{ELECTION_BASE}/{election_id}/activate",
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 200, response.text


def prepare_active_election_with_voter(organizer_token, voter_user):
    election = create_election_as_organizer(organizer_token)
    add_voter_to_election(organizer_token, election["id"], voter_user)
    activate_election(organizer_token, election["id"])
    return election


class TestCreateVote:
    def test_voter_can_vote_when_eligible(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        candidate_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={
                "election_id": election["id"],
                "candidate_id": candidate_id,
            },
            headers=auth_header(voter_token),
        )

        assert response.status_code == 201, response.text

        data = response.json()
        assert data["election_id"] == election["id"]
        assert data["receipt_code"] is not None
        # encrypted_vote is a Paillier ciphertext stored as JSON
        import json
        parsed = json.loads(data["encrypted_vote"])
        assert set(parsed.keys()) == {c["id"] for c in election["candidates"]}

    def test_voter_cannot_vote_twice(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        candidate_id = election["candidates"][0]["id"]

        first_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(voter_token),
        )

        assert first_response.status_code == 201, first_response.text

        second_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(voter_token),
        )

        assert second_response.status_code == 400
        assert "already" in second_response.json()["detail"].lower()

    def test_ineligible_voter_cannot_vote(self, organizer_token, other_voter_token):
        election = create_election_as_organizer(organizer_token)
        set_election_status(election["id"], ElectionStatus.active)

        candidate_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(other_voter_token),
        )

        assert response.status_code == 403

    def test_voter_cannot_vote_in_draft_election(self, organizer_token, voter_user, voter_token):
        election = create_election_as_organizer(organizer_token)
        add_voter_to_election(organizer_token, election["id"], voter_user)

        candidate_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400
        assert "active" in response.json()["detail"].lower()

    def test_candidate_must_belong_to_election(self, organizer_token, voter_user, voter_token):
        election_1 = prepare_active_election_with_voter(organizer_token, voter_user)
        election_2 = create_election_as_organizer(organizer_token)

        wrong_candidate_id = election_2["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={
                "election_id": election_1["id"],
                "candidate_id": wrong_candidate_id,
            },
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400
        assert "candidate" in response.json()["detail"].lower()


class TestVoteHistory:
    def test_voter_can_view_vote_history(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        candidate_id = election["candidates"][0]["id"]

        vote_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(voter_token),
        )

        assert vote_response.status_code == 201, vote_response.text

        response = client.get(
            f"{VOTE_BASE}/history",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert len(data) >= 1
        assert any(item["election_id"] == election["id"] for item in data)

    def test_voter_can_view_vote_details(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        candidate_id = election["candidates"][0]["id"]

        vote_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(voter_token),
        )

        assert vote_response.status_code == 201, vote_response.text

        vote_id = vote_response.json()["id"]

        response = client.get(
            f"{VOTE_BASE}/{vote_id}",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["id"] == vote_id

    def test_voter_cannot_view_other_voters_vote(
        self,
        organizer_token,
        voter_user,
        voter_token,
        other_voter_token,
    ):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        candidate_id = election["candidates"][0]["id"]

        vote_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(voter_token),
        )

        assert vote_response.status_code == 201, vote_response.text

        vote_id = vote_response.json()["id"]

        response = client.get(
            f"{VOTE_BASE}/{vote_id}",
            headers=auth_header(other_voter_token),
        )

        assert response.status_code == 404

    def test_vote_history_invalid_date_period_rejected(self, voter_token):
        response = client.get(
            f"{VOTE_BASE}/history?start_date=2030-01-01&end_date=2020-01-01",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400
        assert "invalid date period" in response.json()["detail"].lower()


def multi_election_payload(num_candidates: int = 3, max_selections: int = 2) -> dict:
    now = datetime.utcnow()
    return {
        "title": unique_text("Multi Select Election"),
        "description": "Multi-select election",
        "start_date": (now - timedelta(minutes=10)).isoformat(),
        "end_date": (now + timedelta(hours=24)).isoformat(),
        "candidates": [
            {"name": unique_text(f"Cand{i}"), "description": f"C{i}", "photo_url": None, "display_order": i + 1}
            for i in range(num_candidates)
        ],
        "ballot_type": "multi",
        "max_selections": max_selections,
    }


def prepare_active_multi_election(organizer_token, voter_users, num_candidates=3, max_selections=2):
    response = client.post(
        f"{ELECTION_BASE}/draft",
        json=multi_election_payload(num_candidates, max_selections),
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 201, response.text
    election = response.json()

    for voter_user in voter_users:
        add_voter_to_election(organizer_token, election["id"], voter_user)

    activate_election(organizer_token, election["id"])
    return election


class TestVoteSelectionContract:
    def test_legacy_candidate_id_single_vote_succeeds(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        candidate = election["candidates"][0]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate["id"]},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        # Legacy receipt behavior preserved.
        assert data["candidate_name"] == candidate["name"]
        assert data["candidate_names"] == [candidate["name"]]
        assert data["abstained"] is False

    def test_candidate_ids_single_selection_succeeds(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        candidate = election["candidates"][0]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": [candidate["id"]]},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["candidate_name"] == candidate["name"]
        assert data["candidate_names"] == [candidate["name"]]
        assert data["abstained"] is False

    def test_both_candidate_fields_rejected(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        candidate_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={
                "election_id": election["id"],
                "candidate_id": candidate_id,
                "candidate_ids": [candidate_id],
            },
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400
        assert "both" in response.json()["detail"].lower() or "either" in response.json()["detail"].lower()

    def test_missing_both_selection_fields_rejected(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"]},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400

    def test_single_ballot_rejects_multiple_selections(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)  # single ballot
        ids = [c["id"] for c in election["candidates"]]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": ids},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400
        assert "single" in response.json()["detail"].lower()

    def test_abstention_succeeds(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": []},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["abstained"] is True
        assert data["candidate_names"] == []
        assert data["candidate_name"] is None

    def test_double_vote_rejected_after_abstention(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)

        first = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": []},
            headers=auth_header(voter_token),
        )
        assert first.status_code == 201, first.text

        second = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": [election["candidates"][0]["id"]]},
            headers=auth_header(voter_token),
        )
        assert second.status_code == 400
        assert "already" in second.json()["detail"].lower()


class TestMultiSelectVoting:
    def test_multi_ballot_accepts_up_to_max_selections(self, organizer_token, voter_user, voter_token):
        election = prepare_active_multi_election(organizer_token, [voter_user], num_candidates=3, max_selections=2)
        ids = [c["id"] for c in election["candidates"]]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": ids[:2]},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert len(data["candidate_names"]) == 2
        assert data["candidate_name"] is None  # more than one selection
        assert data["abstained"] is False

    def test_multi_ballot_rejects_over_max_selections(self, organizer_token, voter_user, voter_token):
        election = prepare_active_multi_election(organizer_token, [voter_user], num_candidates=3, max_selections=2)
        ids = [c["id"] for c in election["candidates"]]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": ids},  # 3 > max 2
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400
        assert "at most" in response.json()["detail"].lower()

    def test_duplicate_candidate_ids_rejected(self, organizer_token, voter_user, voter_token):
        election = prepare_active_multi_election(organizer_token, [voter_user], num_candidates=3, max_selections=2)
        candidate_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": [candidate_id, candidate_id]},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400
        assert "duplicate" in response.json()["detail"].lower()

    def test_candidate_from_another_election_rejected(self, organizer_token, voter_user, voter_token):
        election = prepare_active_multi_election(organizer_token, [voter_user], num_candidates=3, max_selections=2)
        other_election = create_election_as_organizer(organizer_token)
        foreign_id = other_election["candidates"][0]["id"]
        own_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_ids": [own_id, foreign_id]},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 400
        assert "candidate" in response.json()["detail"].lower()

# ---------------------------------------------------------------------------
# Ballot commitment and receipt verification
#
# The commitment covers the ballot's complete ciphertext, so modifying a stored
# ballot invalidates it. It does NOT prove the ballot was counted as cast: the
# backend holds the signing secret.
# ---------------------------------------------------------------------------


def _stored_ballot(vote_id: str):
    from app.models.ballot import Ballot

    db = SessionLocal()
    try:
        return db.query(Ballot).filter(Ballot.id == UUID(vote_id)).first()
    finally:
        db.close()


def _mutate_ballot(vote_id: str, **fields):
    from app.models.ballot import Ballot

    db = SessionLocal()
    try:
        ballot = db.query(Ballot).filter(Ballot.id == UUID(vote_id)).first()
        assert ballot is not None
        for name, value in fields.items():
            setattr(ballot, name, value)
        db.commit()
    finally:
        db.close()


class TestBallotCommitment:
    def test_receipt_returns_a_commitment(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)

        response = client.post(
            VOTE_BASE,
            json={
                "election_id": election["id"],
                "candidate_id": election["candidates"][0]["id"],
            },
            headers=auth_header(voter_token),
        )

        assert response.status_code == 201, response.text
        assert len(response.json()["ballot_commitment"]) == 64

    def test_stored_commitment_equals_the_one_in_the_receipt(
        self, organizer_token, voter_user, voter_token
    ):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        vote = client.post(
            VOTE_BASE,
            json={
                "election_id": election["id"],
                "candidate_id": election["candidates"][0]["id"],
            },
            headers=auth_header(voter_token),
        ).json()

        assert _stored_ballot(vote["id"]).ballot_commitment == vote["ballot_commitment"]

    def test_two_ballots_get_different_commitments(self, organizer_token, voter_user, voter_token):
        """Distinct ballots must never collide, even for the same voter and choice."""
        commitments = set()

        for _ in range(2):
            election = prepare_active_election_with_voter(organizer_token, voter_user)
            response = client.post(
                VOTE_BASE,
                json={
                    "election_id": election["id"],
                    "candidate_id": election["candidates"][0]["id"],
                },
                headers=auth_header(voter_token),
            )
            assert response.status_code == 201, response.text
            commitments.add(response.json()["ballot_commitment"])

        assert len(commitments) == 2


class TestVerifyVote:
    def _cast(self, organizer_token, voter_user, voter_token):
        election = prepare_active_election_with_voter(organizer_token, voter_user)
        response = client.post(
            VOTE_BASE,
            json={
                "election_id": election["id"],
                "candidate_id": election["candidates"][0]["id"],
            },
            headers=auth_header(voter_token),
        )
        assert response.status_code == 201, response.text
        return election, response.json()

    def test_an_untouched_ballot_verifies(self, organizer_token, voter_user, voter_token):
        _, vote = self._cast(organizer_token, voter_user, voter_token)

        response = client.get(
            f"{VOTE_BASE}/{vote['id']}/verify",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["verified"] is True

    def test_a_tampered_ciphertext_fails_verification(
        self, organizer_token, voter_user, voter_token
    ):
        """The property the old salted hash could not provide."""
        _, vote = self._cast(organizer_token, voter_user, voter_token)

        _mutate_ballot(vote["id"], encrypted_vote='{"tampered":{"c":"1","e":0}}')

        response = client.get(
            f"{VOTE_BASE}/{vote['id']}/verify",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["verified"] is False

    def test_a_tampered_receipt_code_fails_verification(
        self, organizer_token, voter_user, voter_token
    ):
        _, vote = self._cast(organizer_token, voter_user, voter_token)

        _mutate_ballot(vote["id"], receipt_code="RCPT-TAMPERED0001")

        assert (
            client.get(
                f"{VOTE_BASE}/{vote['id']}/verify",
                headers=auth_header(voter_token),
            ).json()["verified"]
            is False
        )

    def test_a_tampered_submission_time_fails_verification(
        self, organizer_token, voter_user, voter_token
    ):
        _, vote = self._cast(organizer_token, voter_user, voter_token)

        _mutate_ballot(vote["id"], submitted_at=datetime(2020, 1, 1, 0, 0, 0))

        assert (
            client.get(
                f"{VOTE_BASE}/{vote['id']}/verify",
                headers=auth_header(voter_token),
            ).json()["verified"]
            is False
        )

    def test_a_legacy_commitment_fails_verification(
        self, organizer_token, voter_user, voter_token
    ):
        """Ballots predating the scheme must report failure, never silent success."""
        _, vote = self._cast(organizer_token, voter_user, voter_token)

        _mutate_ballot(vote["id"], ballot_commitment=uuid4().hex)

        assert (
            client.get(
                f"{VOTE_BASE}/{vote['id']}/verify",
                headers=auth_header(voter_token),
            ).json()["verified"]
            is False
        )

    def test_another_voter_cannot_verify_someone_elses_ballot(
        self, organizer_token, voter_user, voter_token, other_voter_token
    ):
        _, vote = self._cast(organizer_token, voter_user, voter_token)

        response = client.get(
            f"{VOTE_BASE}/{vote['id']}/verify",
            headers=auth_header(other_voter_token),
        )

        assert response.status_code == 404

    def test_verification_requires_authentication(
        self, organizer_token, voter_user, voter_token
    ):
        _, vote = self._cast(organizer_token, voter_user, voter_token)

        assert client.get(f"{VOTE_BASE}/{vote['id']}/verify").status_code == 401

    def test_verifying_an_unknown_ballot_returns_404(self, voter_token):
        response = client.get(
            f"{VOTE_BASE}/{uuid4()}/verify",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 404
