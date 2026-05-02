from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.election import Election, ElectionStatus


client = TestClient(app)

ELECTION_BASE = "/elections"
AUTH_BASE = "/auth"


def unique_text(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def register_user(role: str):
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

    data = response.json()
    return data["access_token"]


def auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def teacher_token():
    teacher = register_user("teacher")
    return login_user(teacher["email"])


@pytest.fixture
def student_token():
    student = register_user("student")
    return login_user(student["email"])


def valid_election_payload():
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


def create_election_as_teacher(teacher_token: str):
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


class TestCreateElection:
    def test_teacher_can_create_draft_election_with_candidates(self, teacher_token):
        response = client.post(
            ELECTION_BASE,
            json=valid_election_payload(),
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 201, response.text

        data = response.json()
        assert data["title"] is not None
        assert data["status"] == "draft"
        assert len(data["candidates"]) == 2

    def test_student_cannot_create_election(self, student_token):
        response = client.post(
            ELECTION_BASE,
            json=valid_election_payload(),
            headers=auth_header(student_token),
        )

        assert response.status_code == 403

    def test_create_election_requires_candidates(self, teacher_token):
        payload = valid_election_payload()
        payload["candidates"] = []

        response = client.post(
            ELECTION_BASE,
            json=payload,
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 400
        assert "candidate" in response.json()["detail"].lower()

    def test_create_election_rejects_invalid_date_range(self, teacher_token):
        now = datetime.utcnow()

        payload = valid_election_payload()
        payload["start_date"] = (now + timedelta(hours=3)).isoformat()
        payload["end_date"] = (now + timedelta(hours=1)).isoformat()

        response = client.post(
            ELECTION_BASE,
            json=payload,
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 400
        assert "end date" in response.json()["detail"].lower()


class TestViewElection:
    def test_can_view_election_details(self, teacher_token):
        election = create_election_as_teacher(teacher_token)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert data["id"] == election["id"]
        assert len(data["candidates"]) == 2

    def test_view_missing_election_returns_404(self, teacher_token):
        fake_id = uuid4()

        response = client.get(
            f"{ELECTION_BASE}/{fake_id}",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 404


class TestElectionLists:
    def test_can_view_active_election_list(self, teacher_token):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.active)

        response = client.get(
            f"{ELECTION_BASE}/active",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        election_ids = [item["id"] for item in data]

        assert election["id"] in election_ids

    def test_can_search_active_election_list(self, teacher_token):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.active)

        search_term = election["title"][:8]

        response = client.get(
            f"{ELECTION_BASE}/active?search={search_term}",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert any(search_term.lower() in item["title"].lower() for item in data)

    def test_can_view_election_history(self, teacher_token):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.completed)

        response = client.get(
            f"{ELECTION_BASE}/history",
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        election_ids = [item["id"] for item in data]

        assert election["id"] in election_ids


class TestUpdateElection:
    def test_teacher_can_update_own_draft_election(self, teacher_token):
        election = create_election_as_teacher(teacher_token)

        payload = {
            "title": "Updated Election Title",
            "description": "Updated description",
            "candidates": [
                {
                    "name": unique_text("Charlie"),
                    "description": "Updated candidate",
                    "photo_url": None,
                    "display_order": 1,
                }
            ],
        }

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json=payload,
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert data["title"] == "Updated Election Title"
        assert len(data["candidates"]) == 1

    def test_teacher_cannot_fully_update_active_election(self, teacher_token):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.active)

        payload = {
            "title": "Should Not Update",
        }

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json=payload,
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 400
        assert "draft" in response.json()["detail"].lower()


class TestExtendDeadline:
    def test_teacher_can_extend_active_election_deadline(self, teacher_token):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.active)

        new_end_date = datetime.utcnow() + timedelta(days=2)

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/extend-deadline",
            json={"new_end_date": new_end_date.isoformat()},
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert data["id"] == election["id"]

    def test_cannot_extend_deadline_to_earlier_date(self, teacher_token):
        election = create_election_as_teacher(teacher_token)
        set_election_status(election["id"], ElectionStatus.active)

        old_end_date = datetime.utcnow()

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/extend-deadline",
            json={"new_end_date": old_end_date.isoformat()},
            headers=auth_header(teacher_token),
        )

        assert response.status_code == 400
        assert "later" in response.json()["detail"].lower()