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
RESULT_BASE = "/results"


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
def teacher_user():
    return register_user("teacher")


@pytest.fixture
def teacher_token(teacher_user):
    return login_user(teacher_user["email"])


@pytest.fixture
def second_teacher_token():
    teacher = register_user("teacher")
    return login_user(teacher["email"])


@pytest.fixture
def student_user():
    return register_user("student")


@pytest.fixture
def student_token(student_user):
    return login_user(student_user["email"])


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


def prepare_completed_election_with_vote(teacher_token, student_user, student_token):
    election = create_election_as_teacher(teacher_token)
    add_student_to_election(teacher_token, election["id"], student_user)

    set_election_status(election["id"], ElectionStatus.active)

    candidate_id = election["candidates"][0]["id"]

    vote_response = client.post(
        VOTE_BASE,
        json={
            "election_id": election["id"],
            "candidate_id": candidate_id,
        },
        headers=auth_header(student_token),
    )

    assert vote_response.status_code == 201, vote_response.text

    set_election_status(election["id"], ElectionStatus.completed)

    return election, candidate_id


class TestElectionResults:
    def test_teacher_can_view_completed_election_results(
        self,
        teacher_token,
        student_user,
        student_token,
    ):
        election, voted_candidate_id = prepare_completed_election_with_vote(
            teacher_token,
            student_user,
            student_token,
        )

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert data["election_id"] == election["id"]
        assert data["status"] == "completed"
        assert len(data["results"]) == 2

        voted_candidate_result = next(
            item for item in data["results"]
            if item["candidate_id"] == voted_candidate_id
        )

        assert voted_candidate_result["total_votes"] == 1

    def test_student_can_view_completed_election_results(
        self,
        teacher_token,
        student_user,
        student_token,
    ):
        election, _ = prepare_completed_election_with_vote(
            teacher_token,
            student_user,
            student_token,
        )

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(student_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["election_id"] == election["id"]

    def test_results_not_available_for_active_election(
        self,
        teacher_token,
        student_user,
        student_token,
    ):
        election = create_election_as_teacher(teacher_token)
        add_student_to_election(teacher_token, election["id"], student_user)
        set_election_status(election["id"], ElectionStatus.active)

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 400
        assert "completed" in response.json()["detail"].lower()

    def test_teacher_cannot_view_other_teachers_results(
        self,
        teacher_token,
        second_teacher_token,
        student_user,
        student_token,
    ):
        election, _ = prepare_completed_election_with_vote(
            teacher_token,
            student_user,
            student_token,
        )

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(second_teacher_token),
        )

        assert response.status_code == 403

    def test_missing_election_results_return_404(self, teacher_token):
        fake_id = uuid4()

        response = client.get(
            f"{RESULT_BASE}/elections/{fake_id}",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 404