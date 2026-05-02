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
        "institution_id": f"INST-{suffix}",
        "username": f"{role}_{suffix}",
        "full_name": f"Test {role.title()}",
        "email": f"{role}_{suffix}@test.com",
        "password": "testing123",
    }

    response = client.post(f"{AUTH_BASE}/register", json=payload)
    assert response.status_code in [200, 201], response.text

    return payload


def login_user(email: str, password: str = "testing123") -> str:
    response = client.post(
        f"{AUTH_BASE}/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def teacher_token():
    teacher = register_user("teacher")
    return login_user(teacher["email"])


@pytest.fixture
def student_user():
    return register_user("student")


@pytest.fixture
def student_token(student_user):
    return login_user(student_user["email"])


@pytest.fixture
def other_student_token():
    student = register_user("student")
    return login_user(student["email"])


def valid_election_payload() -> dict:
    now = datetime.utcnow()

    return {
        "title": unique_text("Class Representative Election"),
        "description": "Election for class representative",
        "start_date": (now - timedelta(minutes=10)).isoformat(),
        "end_date": (now + timedelta(hours=3)).isoformat(),
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


def create_election_as_teacher(teacher_token: str) -> dict:
    response = client.post(
        ELECTION_BASE,
        json=valid_election_payload(),
        headers=auth_header(teacher_token),
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


def add_student_to_election(teacher_token: str, election_id: str, student_user: dict):
    response = client.post(
        f"{ELECTION_BASE}/{election_id}/voters",
        json={"institution_id": student_user["institution_id"]},
        headers=auth_header(teacher_token),
    )

    assert response.status_code == 201, response.text
    return response.json()


def prepare_active_election_with_student(teacher_token, student_user):
    election = create_election_as_teacher(teacher_token)
    add_student_to_election(teacher_token, election["id"], student_user)
    set_election_status(election["id"], ElectionStatus.active)
    return election


class TestCreateVote:
    def test_student_can_vote_when_eligible(self, teacher_token, student_user, student_token):
        election = prepare_active_election_with_student(teacher_token, student_user)
        candidate_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={
                "election_id": election["id"],
                "candidate_id": candidate_id,
            },
            headers=auth_header(student_token),
        )

        assert response.status_code == 201, response.text

        data = response.json()
        assert data["election_id"] == election["id"]
        assert data["receipt_code"] is not None
        assert data["encrypted_vote"].startswith("encrypted_placeholder")

    def test_student_cannot_vote_twice(self, teacher_token, student_user, student_token):
        election = prepare_active_election_with_student(teacher_token, student_user)
        candidate_id = election["candidates"][0]["id"]

        first_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(student_token),
        )

        assert first_response.status_code == 201, first_response.text

        second_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(student_token),
        )

        assert second_response.status_code == 400
        assert "already" in second_response.json()["detail"].lower()

    def test_ineligible_student_cannot_vote(self, teacher_token, other_student_token):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.active)

        candidate_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(other_student_token),
        )

        assert response.status_code == 403

    def test_student_cannot_vote_in_draft_election(self, teacher_token, student_user, student_token):
        election = create_election_as_teacher(teacher_token)
        add_student_to_election(teacher_token, election["id"], student_user)

        candidate_id = election["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(student_token),
        )

        assert response.status_code == 400
        assert "active" in response.json()["detail"].lower()

    def test_candidate_must_belong_to_election(self, teacher_token, student_user, student_token):
        election_1 = prepare_active_election_with_student(teacher_token, student_user)
        election_2 = create_election_as_teacher(teacher_token)

        wrong_candidate_id = election_2["candidates"][0]["id"]

        response = client.post(
            VOTE_BASE,
            json={
                "election_id": election_1["id"],
                "candidate_id": wrong_candidate_id,
            },
            headers=auth_header(student_token),
        )

        assert response.status_code == 400
        assert "candidate" in response.json()["detail"].lower()


class TestVoteHistory:
    def test_student_can_view_vote_history(self, teacher_token, student_user, student_token):
        election = prepare_active_election_with_student(teacher_token, student_user)
        candidate_id = election["candidates"][0]["id"]

        vote_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(student_token),
        )

        assert vote_response.status_code == 201, vote_response.text

        response = client.get(
            f"{VOTE_BASE}/history",
            headers=auth_header(student_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert len(data) >= 1
        assert any(item["election_id"] == election["id"] for item in data)

    def test_student_can_view_vote_details(self, teacher_token, student_user, student_token):
        election = prepare_active_election_with_student(teacher_token, student_user)
        candidate_id = election["candidates"][0]["id"]

        vote_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(student_token),
        )

        assert vote_response.status_code == 201, vote_response.text

        vote_id = vote_response.json()["id"]

        response = client.get(
            f"{VOTE_BASE}/{vote_id}",
            headers=auth_header(student_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["id"] == vote_id

    def test_student_cannot_view_other_students_vote(
        self,
        teacher_token,
        student_user,
        student_token,
        other_student_token,
    ):
        election = prepare_active_election_with_student(teacher_token, student_user)
        candidate_id = election["candidates"][0]["id"]

        vote_response = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_id},
            headers=auth_header(student_token),
        )

        assert vote_response.status_code == 201, vote_response.text

        vote_id = vote_response.json()["id"]

        response = client.get(
            f"{VOTE_BASE}/{vote_id}",
            headers=auth_header(other_student_token),
        )

        assert response.status_code == 404