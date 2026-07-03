from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
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