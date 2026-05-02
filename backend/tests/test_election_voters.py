from datetime import datetime, timedelta
from uuid import uuid4, UUID

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.election import Election, ElectionStatus


client = TestClient(app)

AUTH_BASE = "/auth"
ELECTION_BASE = "/elections"


def unique_text(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_user(role: str, status: str = "active") -> dict:
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

    # If you need suspended/pending users for a test, update directly in DB.
    if status != "active":
        db = SessionLocal()
        try:
            from app.models.user import User, UserStatus

            user = db.query(User).filter(User.email == payload["email"]).first()
            assert user is not None
            user.status = UserStatus(status)
            db.commit()
        finally:
            db.close()

    return payload


def login_user(email: str, password: str = "testing123") -> str:
    response = client.post(
        f"{AUTH_BASE}/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def valid_election_payload() -> dict:
    now = datetime.utcnow()

    return {
        "title": unique_text("Class Representative Election"),
        "description": "Election for class representative",
        "start_date": (now + timedelta(hours=1)).isoformat(),
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


@pytest.fixture
def teacher_token():
    teacher = register_user("teacher")
    return login_user(teacher["email"])


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


@pytest.fixture
def teacher_user():
    return register_user("teacher")


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


class TestAddEligibleVoter:
    def test_teacher_can_add_student_to_draft_election(self, teacher_token, student_user):
        election = create_election_as_teacher(teacher_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": student_user["institution_id"]},
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 201, response.text

        data = response.json()
        assert data["election_id"] == election["id"]
        assert data["eligibility_status"] == "eligible"
        assert data["voted_at"] is None

    def test_add_voter_requires_teacher(self, student_token, student_user, teacher_token):
        election = create_election_as_teacher(teacher_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": student_user["institution_id"]},
            headers=auth_header(student_token),
        )

        assert response.status_code == 403

    def test_teacher_cannot_add_voter_to_other_teachers_election(
        self,
        teacher_token,
        second_teacher_token,
        student_user,
    ):
        election = create_election_as_teacher(teacher_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": student_user["institution_id"]},
            headers=auth_header(second_teacher_token),
        )

        assert response.status_code == 403

    def test_cannot_add_voter_to_active_election(self, teacher_token, student_user):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.active)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": student_user["institution_id"]},
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 400
        assert "draft" in response.json()["detail"].lower()

    def test_cannot_add_non_existing_student(self, teacher_token):
        election = create_election_as_teacher(teacher_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": "NON_EXISTING_123"},
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 404

    def test_cannot_add_teacher_as_voter(self, teacher_token, teacher_user):
        election = create_election_as_teacher(teacher_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": teacher_user["institution_id"]},
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 400
        assert "student" in response.json()["detail"].lower()

    def test_cannot_add_same_student_twice(self, teacher_token, student_user):
        election = create_election_as_teacher(teacher_token)

        first_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": student_user["institution_id"]},
            headers=auth_header(teacher_token),
        )

        assert first_response.status_code == 201, first_response.text

        second_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": student_user["institution_id"]},
            headers=auth_header(teacher_token),
        )

        assert second_response.status_code == 400
        assert "already" in second_response.json()["detail"].lower()


class TestViewEligibleVoters:
    def test_teacher_can_view_eligible_voters(self, teacher_token, student_user):
        election = create_election_as_teacher(teacher_token)

        add_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"institution_id": student_user["institution_id"]},
            headers=auth_header(teacher_token),
        )

        assert add_response.status_code == 201, add_response.text

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}/voters",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert len(data) >= 1
        assert any(
            voter["student_institution_id"] == student_user["institution_id"]
            for voter in data
        )

    def test_view_voters_requires_teacher(self, student_token, teacher_token):
        election = create_election_as_teacher(teacher_token)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}/voters",
            headers=auth_header(student_token),
        )

        assert response.status_code == 403

    def test_teacher_cannot_view_other_teachers_voters(
        self,
        teacher_token,
        second_teacher_token,
    ):
        election = create_election_as_teacher(teacher_token)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}/voters",
            headers=auth_header(second_teacher_token),
        )

        assert response.status_code == 403

    def test_view_voters_missing_election_returns_404(self, teacher_token):
        fake_id = uuid4()

        response = client.get(
            f"{ELECTION_BASE}/{fake_id}/voters",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 404