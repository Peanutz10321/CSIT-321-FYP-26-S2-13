from datetime import datetime, timedelta
from uuid import uuid4, UUID

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.election import Election, ElectionStatus
from app.models.election_voter import ElectionVoter
from app.models.audit_log import AuditLog
from app.models.user import User


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
        "external_id": f"INST-{suffix}",
        "username": f"{role}_{suffix}",
        "full_name": f"Test {role.title()}",
        "email": f"{role}_{suffix}@test.com",
        "password": "testing123",
    }

    response = client.post(f"{AUTH_BASE}/register", json=payload)
    assert response.status_code in [200, 201], response.text

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

    return {**payload, **response.json()}


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
def organizer_token():
    organizer = register_user("organizer")
    return login_user(organizer["email"])


@pytest.fixture
def second_organizer_token():
    organizer = register_user("organizer")
    return login_user(organizer["email"])


@pytest.fixture
def voter_user():
    return register_user("voter")


@pytest.fixture
def voter_token(voter_user):
    return login_user(voter_user["email"])


@pytest.fixture
def organizer_user():
    return register_user("organizer")


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


class TestAddEligibleVoter:
    def test_organizer_can_add_voter_to_draft_election(self, organizer_token, voter_user):
        election = create_election_as_organizer(organizer_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text

        data = response.json()
        assert data["election_id"] == election["id"]
        assert data["eligibility_status"] == "eligible"
        assert data["voted_at"] is None

    def test_add_voter_requires_organizer(self, voter_token, voter_user, organizer_token):
        election = create_election_as_organizer(organizer_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(voter_token),
        )

        assert response.status_code == 403

    def test_organizer_cannot_add_voter_to_other_organizers_election(
        self,
        organizer_token,
        second_organizer_token,
        voter_user,
    ):
        election = create_election_as_organizer(organizer_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(second_organizer_token),
        )

        assert response.status_code == 403

    def test_cannot_add_voter_to_active_election(self, organizer_token, voter_user):
        election = create_election_as_organizer(organizer_token)
        set_election_status(election["id"], ElectionStatus.active)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "draft" in response.json()["detail"].lower()

    def test_cannot_add_non_existing_voter(self, organizer_token):
        election = create_election_as_organizer(organizer_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": "NON_EXISTING_123"},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 404

    def test_cannot_add_organizer_as_voter(self, organizer_token, organizer_user):
        election = create_election_as_organizer(organizer_token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": organizer_user["external_id"]},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "voter" in response.json()["detail"].lower()

    def test_cannot_add_same_voter_twice(self, organizer_token, voter_user):
        election = create_election_as_organizer(organizer_token)

        first_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )

        assert first_response.status_code == 201, first_response.text

        second_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )

        assert second_response.status_code == 400
        assert "already" in second_response.json()["detail"].lower()


class TestViewEligibleVoters:
    def test_organizer_can_view_eligible_voters(self, organizer_token, voter_user):
        election = create_election_as_organizer(organizer_token)

        add_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )

        assert add_response.status_code == 201, add_response.text

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}/voters",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert len(data) >= 1
        assert any(
            voter["voter_external_id"] == voter_user["external_id"]
            for voter in data
        )

    def test_view_voters_requires_organizer(self, voter_token, organizer_token):
        election = create_election_as_organizer(organizer_token)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}/voters",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 403

    def test_organizer_cannot_view_other_organizers_voters(
        self,
        organizer_token,
        second_organizer_token,
    ):
        election = create_election_as_organizer(organizer_token)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}/voters",
            headers=auth_header(second_organizer_token),
        )

        assert response.status_code == 403

    def test_view_voters_missing_election_returns_404(self, organizer_token):
        fake_id = uuid4()

        response = client.get(
            f"{ELECTION_BASE}/{fake_id}/voters",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 404


def eligibility_events(election_id: str) -> list[dict]:
    """Read eligibility_changed audit rows for an election, detached to plain dicts."""
    db = SessionLocal()
    try:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "eligibility_changed",
                AuditLog.entity_id == UUID(election_id),
            )
            .all()
        )
        return [
            {
                "actor_user_id": row.actor_user_id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "details": row.details or "",
            }
            for row in rows
        ]
    finally:
        db.close()


class TestEligibilityAudit:
    def test_add_voter_creates_single_eligibility_event(self, voter_user):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        election = create_election_as_organizer(token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(token),
        )
        assert response.status_code == 201, response.text

        events = eligibility_events(election["id"])
        assert len(events) == 1

        event = events[0]
        assert event["actor_user_id"] == UUID(organizer["id"])          # actor is organizer
        assert event["entity_type"] == "election"                       # entity type
        assert event["entity_id"] == UUID(election["id"])               # entity id
        assert "added" in event["details"]                              # change type
        assert voter_user["id"] in event["details"]                     # target user UUID

    def test_event_details_contain_no_sensitive_data(self, voter_user):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        election = create_election_as_organizer(token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(token),
        )
        assert response.status_code == 201, response.text

        details = eligibility_events(election["id"])[0]["details"]
        # Only the change type and the target user UUID — nothing else.
        for forbidden in [
            voter_user["email"],
            voter_user["username"],
            voter_user["full_name"],
            voter_user["external_id"],
            token,  # no JWT/session material
        ]:
            assert forbidden not in details

    def test_bulk_active_create_creates_event_per_voter(self):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        voter_a = register_user("voter")
        voter_b = register_user("voter")

        payload = valid_election_payload()
        payload["eligible_voter_external_ids"] = [voter_a["external_id"], voter_b["external_id"]]

        response = client.post(ELECTION_BASE, json=payload, headers=auth_header(token))
        assert response.status_code == 201, response.text
        election = response.json()

        events = eligibility_events(election["id"])
        assert len(events) == 2
        details_blob = " ".join(event["details"] for event in events)
        assert voter_a["id"] in details_blob
        assert voter_b["id"] in details_blob
        for event in events:
            assert event["actor_user_id"] == UUID(organizer["id"])
            assert event["entity_type"] == "election"
            assert event["entity_id"] == UUID(election["id"])
            assert "added" in event["details"]

    def test_duplicate_add_creates_no_second_event(self, voter_user):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        election = create_election_as_organizer(token)

        first = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(token),
        )
        assert first.status_code == 201, first.text

        second = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(token),
        )
        assert second.status_code == 400

        # The no-op duplicate must not add a second event.
        assert len(eligibility_events(election["id"])) == 1

    def test_non_owner_attempt_creates_no_event(self, voter_user):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        other = register_user("organizer")
        other_token = login_user(other["email"])
        election = create_election_as_organizer(token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(other_token),
        )
        assert response.status_code == 403

        assert eligibility_events(election["id"]) == []

    def test_voter_attempt_creates_no_event(self, voter_user, voter_token):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        election = create_election_as_organizer(token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(voter_token),
        )
        assert response.status_code == 403

        assert eligibility_events(election["id"]) == []

    def test_invalid_voter_creates_no_event(self):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        election = create_election_as_organizer(token)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": "NON_EXISTING_123"},
            headers=auth_header(token),
        )
        assert response.status_code == 404

        assert eligibility_events(election["id"]) == []

    def test_invalid_election_creates_no_event(self, voter_user):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        fake_id = uuid4()

        response = client.post(
            f"{ELECTION_BASE}/{fake_id}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(token),
        )
        assert response.status_code == 404

        assert eligibility_events(str(fake_id)) == []

    def test_failed_bulk_add_leaves_no_membership_or_audit(self):
        organizer = register_user("organizer")
        token = login_user(organizer["email"])
        good_voter = register_user("voter")

        payload = valid_election_payload()
        # A valid voter followed by a non-existent one: the whole create must roll back.
        payload["eligible_voter_external_ids"] = [good_voter["external_id"], "NON_EXISTING_XYZ"]

        response = client.post(ELECTION_BASE, json=payload, headers=auth_header(token))
        assert response.status_code == 404

        db = SessionLocal()
        try:
            good_user = db.query(User).filter(User.external_id == good_voter["external_id"]).first()
            assert good_user is not None
            # No membership survived for the good voter.
            memberships = (
                db.query(ElectionVoter)
                .filter(ElectionVoter.voter_id == good_user.id)
                .all()
            )
            assert memberships == []
            # No eligibility audit event survived either.
            audit_rows = (
                db.query(AuditLog)
                .filter(
                    AuditLog.actor_user_id == UUID(organizer["id"]),
                    AuditLog.action == "eligibility_changed",
                )
                .all()
            )
            assert audit_rows == []
        finally:
            db.close()