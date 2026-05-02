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
        json={
            "email": email,
            "password": password,
        },
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
def second_teacher_user():
    return register_user("teacher")


@pytest.fixture
def second_teacher_token(second_teacher_user):
    return login_user(second_teacher_user["email"])


@pytest.fixture
def student_user():
    return register_user("student")


@pytest.fixture
def student_token(student_user):
    return login_user(student_user["email"])


@pytest.fixture
def second_student_user():
    return register_user("student")


@pytest.fixture
def second_student_token(second_student_user):
    return login_user(second_student_user["email"])


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


def add_student_to_election(
    teacher_token: str,
    election_id: str,
    student_user: dict,
):
    response = client.post(
        f"{ELECTION_BASE}/{election_id}/voters",
        json={"institution_id": student_user["institution_id"]},
        headers=auth_header(teacher_token),
    )

    assert response.status_code == 201, response.text
    return response.json()


class TestTeacherElectionVisibility:
    def test_teacher_only_sees_own_active_elections(
        self,
        teacher_token,
        second_teacher_token,
    ):
        own_election = create_election_as_teacher(teacher_token)
        other_election = create_election_as_teacher(second_teacher_token)

        set_election_status(own_election["id"], ElectionStatus.active)
        set_election_status(other_election["id"], ElectionStatus.active)

        response = client.get(
            f"{ELECTION_BASE}/active",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        election_ids = [item["id"] for item in response.json()]

        assert own_election["id"] in election_ids
        assert other_election["id"] not in election_ids

    def test_teacher_only_sees_own_election_history(
        self,
        teacher_token,
        second_teacher_token,
    ):
        own_election = create_election_as_teacher(teacher_token)
        other_election = create_election_as_teacher(second_teacher_token)

        set_election_status(own_election["id"], ElectionStatus.completed)
        set_election_status(other_election["id"], ElectionStatus.completed)

        response = client.get(
            f"{ELECTION_BASE}/history",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        election_ids = [item["id"] for item in response.json()]

        assert own_election["id"] in election_ids
        assert other_election["id"] not in election_ids

    def test_teacher_can_view_own_election_details(self, teacher_token):
        election = create_election_as_teacher(teacher_token)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["id"] == election["id"]

    def test_teacher_cannot_view_other_teachers_election_details(
        self,
        teacher_token,
        second_teacher_token,
    ):
        other_election = create_election_as_teacher(second_teacher_token)

        response = client.get(
            f"{ELECTION_BASE}/{other_election['id']}",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 403


class TestStudentElectionVisibility:
    def test_student_only_sees_eligible_active_elections(
        self,
        teacher_token,
        student_user,
        student_token,
    ):
        eligible_election = create_election_as_teacher(teacher_token)
        non_eligible_election = create_election_as_teacher(teacher_token)

        add_student_to_election(
            teacher_token,
            eligible_election["id"],
            student_user,
        )

        set_election_status(eligible_election["id"], ElectionStatus.active)
        set_election_status(non_eligible_election["id"], ElectionStatus.active)

        response = client.get(
            f"{ELECTION_BASE}/active",
            headers=auth_header(student_token),
        )

        assert response.status_code == 200, response.text

        election_ids = [item["id"] for item in response.json()]

        assert eligible_election["id"] in election_ids
        assert non_eligible_election["id"] not in election_ids

    def test_student_only_sees_eligible_election_history(
        self,
        teacher_token,
        student_user,
        student_token,
    ):
        eligible_election = create_election_as_teacher(teacher_token)
        non_eligible_election = create_election_as_teacher(teacher_token)

        add_student_to_election(
            teacher_token,
            eligible_election["id"],
            student_user,
        )

        set_election_status(eligible_election["id"], ElectionStatus.completed)
        set_election_status(non_eligible_election["id"], ElectionStatus.completed)

        response = client.get(
            f"{ELECTION_BASE}/history",
            headers=auth_header(student_token),
        )

        assert response.status_code == 200, response.text

        election_ids = [item["id"] for item in response.json()]

        assert eligible_election["id"] in election_ids
        assert non_eligible_election["id"] not in election_ids

    def test_student_can_view_eligible_active_election_details(
        self,
        teacher_token,
        student_user,
        student_token,
    ):
        election = create_election_as_teacher(teacher_token)

        add_student_to_election(
            teacher_token,
            election["id"],
            student_user,
        )

        set_election_status(election["id"], ElectionStatus.active)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}",
            headers=auth_header(student_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["id"] == election["id"]

    def test_student_cannot_view_non_eligible_active_election_details(
        self,
        teacher_token,
        student_token,
    ):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.active)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}",
            headers=auth_header(student_token),
        )

        assert response.status_code == 403

    def test_student_can_view_eligible_completed_election_details(
        self,
        teacher_token,
        student_user,
        student_token,
    ):
        election = create_election_as_teacher(teacher_token)

        add_student_to_election(
            teacher_token,
            election["id"],
            student_user,
        )

        set_election_status(election["id"], ElectionStatus.completed)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}",
            headers=auth_header(student_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["id"] == election["id"]

    def test_student_cannot_view_non_eligible_completed_election_details(
        self,
        teacher_token,
        student_token,
    ):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.completed)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}",
            headers=auth_header(student_token),
        )

        assert response.status_code == 403