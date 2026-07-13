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
def organizer_token():
    organizer = register_user("organizer")
    return login_user(organizer["email"])


@pytest.fixture
def voter_token():
    voter = register_user("voter")
    return login_user(voter["email"])

@pytest.fixture
def voter_user():
    return register_user("voter")


def valid_election_payload():
    now = datetime.utcnow()

    return {
        "title": unique_text("Class Representative Election"),
        "description": "Election for class representative",
        "start_date": (now + timedelta(hours=1)).isoformat(),
        "end_date": (now + timedelta(days=2)).isoformat(),
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


def create_election_as_organizer(organizer_token: str):
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


class TestCreateElection:
    def test_organizer_can_create_draft_election_with_candidates(self, organizer_token):
        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=valid_election_payload(),
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text

        data = response.json()
        assert data["title"] is not None
        assert data["status"] == "draft"
        assert len(data["candidates"]) == 2

    def test_organizer_can_create_active_election_with_voters(self, organizer_token, voter_user):
        payload = valid_election_payload()
        payload["eligible_voter_external_ids"] = [voter_user["external_id"]]

        response = client.post(
            ELECTION_BASE,
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text

        data = response.json()
        assert data["status"] == "active"
        assert len(data["candidates"]) == 2

    def test_create_active_election_requires_eligible_voter(self, organizer_token):
        response = client.post(
            ELECTION_BASE,
            json=valid_election_payload(),
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "eligible voter" in response.json()["detail"].lower()

    def test_voter_cannot_create_election(self, voter_token):
        response = client.post(
            ELECTION_BASE,
            json=valid_election_payload(),
            headers=auth_header(voter_token),
        )

        assert response.status_code == 403

    def test_create_election_requires_candidates(self, organizer_token):
        payload = valid_election_payload()
        payload["candidates"] = []

        response = client.post(
            ELECTION_BASE,
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "candidate" in response.json()["detail"].lower()

    def test_create_election_rejects_invalid_date_range(self, organizer_token):
        now = datetime.utcnow()

        payload = valid_election_payload()
        payload["start_date"] = (now + timedelta(hours=3)).isoformat()
        payload["end_date"] = (now + timedelta(hours=1)).isoformat()

        response = client.post(
            ELECTION_BASE,
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "end date" in response.json()["detail"].lower()


class TestViewElection:
    def test_can_view_election_details(self, organizer_token):
        election = create_election_as_organizer(organizer_token)

        response = client.get(
            f"{ELECTION_BASE}/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert data["id"] == election["id"]
        assert len(data["candidates"]) == 2

    def test_view_missing_election_returns_404(self, organizer_token):
        fake_id = uuid4()

        response = client.get(
            f"{ELECTION_BASE}/{fake_id}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 404


class TestElectionLists:
    def test_can_view_active_election_list(self, organizer_token):
        election = create_election_as_organizer(organizer_token)
        set_election_status(election["id"], ElectionStatus.active)

        response = client.get(
            f"{ELECTION_BASE}/active",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        election_ids = [item["id"] for item in data]

        assert election["id"] in election_ids

    def test_can_search_active_election_list(self, organizer_token):
        election = create_election_as_organizer(organizer_token)
        set_election_status(election["id"], ElectionStatus.active)

        search_term = election["title"][:8]

        response = client.get(
            f"{ELECTION_BASE}/active?search={search_term}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert any(search_term.lower() in item["title"].lower() for item in data)

    def test_can_view_election_history(self, organizer_token):
        election = create_election_as_organizer(organizer_token)
        set_election_status(election["id"], ElectionStatus.completed)

        response = client.get(
            f"{ELECTION_BASE}/history",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        election_ids = [item["id"] for item in data]

        assert election["id"] in election_ids


class TestUpdateElection:
    def test_organizer_can_update_own_draft_election(self, organizer_token):
        election = create_election_as_organizer(organizer_token)

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
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert data["title"] == "Updated Election Title"
        assert len(data["candidates"]) == 1

    def test_organizer_cannot_fully_update_active_election(self, organizer_token):
        election = create_election_as_organizer(organizer_token)
        set_election_status(election["id"], ElectionStatus.active)

        payload = {
            "title": "Should Not Update",
        }

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "draft" in response.json()["detail"].lower()


class TestExtendDeadline:
    def test_organizer_can_extend_active_election_deadline(self, organizer_token):
        election = create_election_as_organizer(organizer_token)
        set_election_status(election["id"], ElectionStatus.active)

        new_end_date = datetime.utcnow() + timedelta(days=2)

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/extend-deadline",
            json={"new_end_date": new_end_date.isoformat()},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text

        data = response.json()
        assert data["id"] == election["id"]

    def test_cannot_extend_deadline_to_earlier_date(self, organizer_token):
        election = create_election_as_organizer(organizer_token)
        set_election_status(election["id"], ElectionStatus.active)

        old_end_date = datetime.utcnow()

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/extend-deadline",
            json={"new_end_date": old_end_date.isoformat()},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "earlier" in response.json()["detail"].lower()

class TestElectionStatusTransitions:
    def test_organizer_can_activate_own_draft_election(self, organizer_token, voter_user):
        election = create_election_as_organizer(organizer_token)

        add_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )
        assert add_response.status_code == 201, add_response.text

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/activate",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "active"

    def test_cannot_activate_without_eligible_voter(self, organizer_token):
        election = create_election_as_organizer(organizer_token)

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/activate",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "eligible voter" in response.json()["detail"].lower()

    def test_organizer_can_complete_active_election(self, organizer_token, voter_user):
        election = create_election_as_organizer(organizer_token)

        add_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )
        assert add_response.status_code == 201, add_response.text

        activate_response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/activate",
            headers=auth_header(organizer_token),
        )
        assert activate_response.status_code == 200, activate_response.text

        complete_response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/complete",
            headers=auth_header(organizer_token),
        )

        assert complete_response.status_code == 200, complete_response.text
        assert complete_response.json()["status"] == "completed"

    def test_cannot_complete_draft_election(self, organizer_token):
        election = create_election_as_organizer(organizer_token)

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/complete",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "active" in response.json()["detail"].lower()


def _expire_election(election_id: str):
    db = SessionLocal()
    try:
        row = db.query(Election).filter(Election.id == UUID(election_id)).first()
        row.end_date = datetime.utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()


class TestElectionListFiltering:
    def test_active_list_excludes_expired_elections(self, organizer_token, voter_user):
        election = create_election_as_organizer(organizer_token)
        client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )
        client.patch(
            f"{ELECTION_BASE}/{election['id']}/activate",
            headers=auth_header(organizer_token),
        )
        _expire_election(election["id"])

        response = client.get(f"{ELECTION_BASE}/active", headers=auth_header(organizer_token))

        assert response.status_code == 200, response.text
        ids = [item["id"] for item in response.json()]
        assert election["id"] not in ids

    def test_history_includes_completed_excludes_running(self, organizer_token):
        completed = create_election_as_organizer(organizer_token)
        set_election_status(completed["id"], ElectionStatus.completed)

        running = create_election_as_organizer(organizer_token)
        set_election_status(running["id"], ElectionStatus.active)

        response = client.get(f"{ELECTION_BASE}/history", headers=auth_header(organizer_token))

        assert response.status_code == 200, response.text
        ids = [item["id"] for item in response.json()]
        assert completed["id"] in ids
        assert running["id"] not in ids


class TestDraftRelaxation:
    def test_draft_save_with_no_candidates_succeeds(self, organizer_token):
        payload = valid_election_payload()
        payload["candidates"] = []

        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "draft"

    def test_draft_save_with_only_title_succeeds(self, organizer_token):
        payload = {
            "title": unique_text("Draft With Only Title"),
            "description": None,
            "start_date": datetime.utcnow().isoformat(),
            "candidates": [],
        }

        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["status"] == "draft"
        assert data["end_date"] is None

    def test_create_active_election_requires_end_date(self, organizer_token, voter_user):
        payload = valid_election_payload()
        payload["eligible_voter_external_ids"] = [voter_user["external_id"]]
        payload.pop("end_date")

        response = client.post(
            ELECTION_BASE,
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400


class TestDateFilter:
    def test_history_invalid_date_period_rejected(self, organizer_token):
        response = client.get(
            f"{ELECTION_BASE}/history?start_date=2030-01-01&end_date=2020-01-01",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "invalid date period" in response.json()["detail"].lower()


class TestBallotConfiguration:
    def test_default_ballot_configuration_is_single(self, organizer_token):
        """A create request without the new fields defaults to a single-choice
        ballot with max_selections == 1 (backward compatible)."""
        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=valid_election_payload(),
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["ballot_type"] == "single"
        assert data["max_selections"] == 1

    def test_explicit_single_ballot_succeeds(self, organizer_token):
        payload = valid_election_payload()
        payload["ballot_type"] = "single"
        payload["max_selections"] = 1

        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["ballot_type"] == "single"
        assert data["max_selections"] == 1

    def test_explicit_multi_ballot_succeeds(self, organizer_token):
        payload = valid_election_payload()  # two candidates
        payload["ballot_type"] = "multi"
        payload["max_selections"] = 2

        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["ballot_type"] == "multi"
        assert data["max_selections"] == 2

    def test_ballot_fields_present_in_detail_and_list_responses(self, organizer_token):
        payload = valid_election_payload()
        payload["ballot_type"] = "multi"
        payload["max_selections"] = 2

        create = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )
        assert create.status_code == 201, create.text
        election = create.json()
        assert election["ballot_type"] == "multi"
        assert election["max_selections"] == 2

        detail = client.get(
            f"{ELECTION_BASE}/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["ballot_type"] == "multi"
        assert detail.json()["max_selections"] == 2

        drafts = client.get(
            f"{ELECTION_BASE}/drafts",
            headers=auth_header(organizer_token),
        )
        assert drafts.status_code == 200, drafts.text
        match = next(item for item in drafts.json() if item["id"] == election["id"])
        assert match["ballot_type"] == "multi"
        assert match["max_selections"] == 2

    def test_draft_update_can_change_ballot_configuration(self, organizer_token):
        election = create_election_as_organizer(organizer_token)  # default single/1, two candidates
        assert election["ballot_type"] == "single"

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json={"ballot_type": "multi", "max_selections": 2},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ballot_type"] == "multi"
        assert data["max_selections"] == 2

    def test_single_ballot_with_nonunit_max_selections_rejected(self, organizer_token):
        payload = valid_election_payload()
        payload["ballot_type"] = "single"
        payload["max_selections"] = 2

        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "single" in response.json()["detail"].lower()

    def test_zero_or_negative_max_selections_rejected(self, organizer_token):
        for bad_value in (0, -1):
            payload = valid_election_payload()
            payload["ballot_type"] = "multi"
            payload["max_selections"] = bad_value

            response = client.post(
                f"{ELECTION_BASE}/draft",
                json=payload,
                headers=auth_header(organizer_token),
            )

            assert response.status_code == 400, response.text
            assert "max_selections" in response.json()["detail"].lower()

    def test_activation_rejects_max_selections_exceeding_candidate_count(
        self, organizer_token, voter_user
    ):
        # Draft is allowed to hold max_selections beyond the (not-yet-final) candidates.
        payload = valid_election_payload()  # two candidates
        payload["ballot_type"] = "multi"
        payload["max_selections"] = 3

        create = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )
        assert create.status_code == 201, create.text
        election = create.json()

        add = client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter_user["external_id"]},
            headers=auth_header(organizer_token),
        )
        assert add.status_code == 201, add.text

        # Activation finalizes the candidate list: 3 > 2 candidates must be rejected.
        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/activate",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "candidate" in response.json()["detail"].lower()

    def test_title_only_draft_gets_default_ballot_configuration(self, organizer_token):
        payload = {
            "title": unique_text("Draft With Only Title"),
            "description": None,
            "start_date": datetime.utcnow().isoformat(),
            "candidates": [],
        }

        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["status"] == "draft"
        assert data["ballot_type"] == "single"
        assert data["max_selections"] == 1


def create_ballot_draft(organizer_token: str, ballot_type: str, max_selections: int) -> dict:
    """Create a draft election with an explicit ballot configuration. Drafts do not
    enforce the candidate-count rule, so this can hold e.g. multi/3 with 2 candidates."""
    payload = valid_election_payload()
    payload["ballot_type"] = ballot_type
    payload["max_selections"] = max_selections

    response = client.post(
        f"{ELECTION_BASE}/draft",
        json=payload,
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def put_election(organizer_token: str, election_id: str, body: dict):
    return client.put(
        f"{ELECTION_BASE}/{election_id}",
        json=body,
        headers=auth_header(organizer_token),
    )


def get_election(organizer_token: str, election_id: str) -> dict:
    response = client.get(
        f"{ELECTION_BASE}/{election_id}",
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestBallotPartialUpdate:
    """PUT /elections/{id} must merge optional ballot fields with the stored values
    using explicit `is not None` checks — never truthiness — so a 0 is honored rather
    than falling back, and a partial update validates against the effective config."""

    def test_update_only_max_selections_keeps_multi(self, organizer_token):
        # Case 1: multi/3, update only max_selections=2 -> multi/2.
        election = create_ballot_draft(organizer_token, "multi", 3)

        response = put_election(organizer_token, election["id"], {"max_selections": 2})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ballot_type"] == "multi"
        assert data["max_selections"] == 2

        fresh = get_election(organizer_token, election["id"])
        assert fresh["ballot_type"] == "multi"
        assert fresh["max_selections"] == 2

    def test_update_only_ballot_type_uses_existing_max(self, organizer_token):
        # Case 2: multi/3, update only ballot_type=single -> 400 (effective max stays 3).
        election = create_ballot_draft(organizer_token, "multi", 3)

        response = put_election(organizer_token, election["id"], {"ballot_type": "single"})
        assert response.status_code == 400
        assert "single" in response.json()["detail"].lower()

        fresh = get_election(organizer_token, election["id"])
        assert fresh["ballot_type"] == "multi"
        assert fresh["max_selections"] == 3

    def test_update_only_max_on_single_is_rejected(self, organizer_token):
        # Case 3: single/1, update only max_selections=2 -> 400.
        election = create_ballot_draft(organizer_token, "single", 1)

        response = put_election(organizer_token, election["id"], {"max_selections": 2})
        assert response.status_code == 400
        assert "single" in response.json()["detail"].lower()

        fresh = get_election(organizer_token, election["id"])
        assert fresh["ballot_type"] == "single"
        assert fresh["max_selections"] == 1

    def test_update_zero_max_selections_does_not_fall_back(self, organizer_token):
        # Case 4: single/1, update max_selections=0 -> 400; zero must NOT fall back to 1.
        election = create_ballot_draft(organizer_token, "single", 1)

        response = put_election(organizer_token, election["id"], {"max_selections": 0})
        assert response.status_code == 400
        assert "max_selections" in response.json()["detail"].lower()

        fresh = get_election(organizer_token, election["id"])
        assert fresh["ballot_type"] == "single"
        assert fresh["max_selections"] == 1

    def test_update_both_fields_atomically_succeeds(self, organizer_token):
        # Case 5: multi/3, update both ballot_type=single and max_selections=1 -> ok.
        election = create_ballot_draft(organizer_token, "multi", 3)

        response = put_election(
            organizer_token,
            election["id"],
            {"ballot_type": "single", "max_selections": 1},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ballot_type"] == "single"
        assert data["max_selections"] == 1

        fresh = get_election(organizer_token, election["id"])
        assert fresh["ballot_type"] == "single"
        assert fresh["max_selections"] == 1

    def test_rejected_update_leaves_configuration_and_other_fields_unchanged(self, organizer_token):
        # Case 6: a rejected update rolls back atomically — neither the ballot config
        # nor an accompanying title change is persisted.
        election = create_ballot_draft(organizer_token, "multi", 3)
        original_title = election["title"]

        response = put_election(
            organizer_token,
            election["id"],
            {"title": "Should Not Persist", "ballot_type": "single"},
        )
        assert response.status_code == 400

        fresh = get_election(organizer_token, election["id"])
        assert fresh["ballot_type"] == "multi"
        assert fresh["max_selections"] == 3
        assert fresh["title"] == original_title

    def test_active_create_with_valid_multi_configuration_succeeds(self, organizer_token, voter_user):
        payload = valid_election_payload()  # two candidates
        payload["eligible_voter_external_ids"] = [voter_user["external_id"]]
        payload["ballot_type"] = "multi"
        payload["max_selections"] = 2

        response = client.post(ELECTION_BASE, json=payload, headers=auth_header(organizer_token))
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["status"] == "active"
        assert data["ballot_type"] == "multi"
        assert data["max_selections"] == 2

    def test_active_create_rejects_max_selections_exceeding_candidates(self, organizer_token, voter_user):
        payload = valid_election_payload()  # two candidates
        payload["eligible_voter_external_ids"] = [voter_user["external_id"]]
        payload["ballot_type"] = "multi"
        payload["max_selections"] = 3  # exceeds the two-candidate final list

        response = client.post(ELECTION_BASE, json=payload, headers=auth_header(organizer_token))
        assert response.status_code == 400
        assert "candidate" in response.json()["detail"].lower()

    def test_ballot_type_serializes_as_plain_string_in_detail_and_list(self, organizer_token):
        single = create_ballot_draft(organizer_token, "single", 1)
        multi = create_ballot_draft(organizer_token, "multi", 2)

        single_detail = get_election(organizer_token, single["id"])
        multi_detail = get_election(organizer_token, multi["id"])
        assert single_detail["ballot_type"] == "single"
        assert multi_detail["ballot_type"] == "multi"

        drafts = client.get(f"{ELECTION_BASE}/drafts", headers=auth_header(organizer_token))
        assert drafts.status_code == 200, drafts.text
        by_id = {item["id"]: item for item in drafts.json()}
        assert by_id[single["id"]]["ballot_type"] == "single"
        assert by_id[multi["id"]]["ballot_type"] == "multi"
        for item in drafts.json():
            assert item["ballot_type"] in ("single", "multi")