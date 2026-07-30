from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from tests.factories import provision_from_payload
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

    # Non-voter accounts are inserted directly because this test needs a fixture,
    # not another assertion of the public organizer-registration flow.
    if role != "voter":
        return {**payload, **provision_from_payload(payload)}

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

    # An election is completed only by the deadline-driven finalize that runs when
    # its results are requested; there is no manual /complete or /close transition
    # to test here. That lifecycle transition is covered end to end by
    # tests/test_results.py::TestAutoFinalizeExpiredElection.


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


def draft_ids(organizer_token: str) -> list[str]:
    response = client.get(f"{ELECTION_BASE}/drafts", headers=auth_header(organizer_token))
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()]


def voter_external_ids(organizer_token: str, election_id: str) -> set[str]:
    response = client.get(
        f"{ELECTION_BASE}/{election_id}/voters",
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 200, response.text
    return {item["voter_external_id"] for item in response.json()}


def eligibility_details(election_id: str) -> list[str]:
    """The details blob of every eligibility_changed event for an election."""
    from app.models.audit_log import AuditLog

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
        return [row.details or "" for row in rows]
    finally:
        db.close()


class TestDraftLifecycle:
    """Save -> resume -> save again -> publish, all on a single election row.

    The organizer edits one draft: re-saving must update it in place rather than
    forking a new one, and publishing must promote that same row to active rather
    than creating a second election alongside it.
    """

    def test_new_draft_saves_candidates_and_eligible_voters(self, organizer_token):
        voter = register_user("voter")

        payload = valid_election_payload()
        payload["eligible_voter_external_ids"] = [voter["external_id"]]

        response = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 201, response.text

        draft = response.json()
        assert draft["status"] == "draft"
        assert len(draft["candidates"]) == 2
        assert voter_external_ids(organizer_token, draft["id"]) == {voter["external_id"]}

    def test_saving_an_opened_draft_updates_the_same_id(self, organizer_token):
        voter = register_user("voter")
        draft = create_election_as_organizer(organizer_token)

        response = put_election(
            organizer_token,
            draft["id"],
            {
                "title": "Resumed Draft",
                "candidates": [{"name": unique_text("Charlie"), "display_order": 1}],
                "eligible_voter_external_ids": [voter["external_id"]],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["id"] == draft["id"]

        fresh = get_election(organizer_token, draft["id"])
        assert fresh["title"] == "Resumed Draft"
        assert fresh["status"] == "draft"
        assert len(fresh["candidates"]) == 1
        assert voter_external_ids(organizer_token, draft["id"]) == {voter["external_id"]}

    def test_saving_an_existing_draft_creates_no_duplicate(self, organizer_token):
        draft = create_election_as_organizer(organizer_token)
        before = draft_ids(organizer_token)

        for title in ["Second Save", "Third Save"]:
            response = put_election(organizer_token, draft["id"], {"title": title})
            assert response.status_code == 200, response.text

        after = draft_ids(organizer_token)
        assert after == before
        assert after.count(draft["id"]) == 1

    def test_eligible_voters_are_synchronized_on_save(self, organizer_token):
        kept = register_user("voter")
        dropped = register_user("voter")
        added = register_user("voter")

        draft = create_election_as_organizer(organizer_token)

        first = put_election(
            organizer_token,
            draft["id"],
            {"eligible_voter_external_ids": [kept["external_id"], dropped["external_id"]]},
        )
        assert first.status_code == 200, first.text
        assert voter_external_ids(organizer_token, draft["id"]) == {
            kept["external_id"],
            dropped["external_id"],
        }

        # Same list minus `dropped`, plus `added`: the stored set must match exactly.
        second = put_election(
            organizer_token,
            draft["id"],
            {"eligible_voter_external_ids": [kept["external_id"], added["external_id"]]},
        )
        assert second.status_code == 200, second.text
        assert voter_external_ids(organizer_token, draft["id"]) == {
            kept["external_id"],
            added["external_id"],
        }

        details = eligibility_details(draft["id"])
        # Two adds, then one add and one removal - `kept` is untouched the second time.
        assert sum("added" in blob for blob in details) == 3
        assert sum("removed" in blob for blob in details) == 1
        removed_blob = next(blob for blob in details if "removed" in blob)
        assert dropped["id"] in removed_blob

    def test_omitting_eligible_voters_leaves_the_list_untouched(self, organizer_token):
        voter = register_user("voter")
        draft = create_election_as_organizer(organizer_token)

        seeded = put_election(
            organizer_token,
            draft["id"],
            {"eligible_voter_external_ids": [voter["external_id"]]},
        )
        assert seeded.status_code == 200, seeded.text

        # A request that never mentions eligibility must not clear it.
        response = put_election(organizer_token, draft["id"], {"title": "Title Only"})
        assert response.status_code == 200, response.text
        assert voter_external_ids(organizer_token, draft["id"]) == {voter["external_id"]}

    def test_invalid_voter_id_causes_no_partial_update(self, organizer_token):
        existing = register_user("voter")
        good = register_user("voter")
        draft = create_election_as_organizer(organizer_token)
        original_title = draft["title"]

        seeded = put_election(
            organizer_token,
            draft["id"],
            {"eligible_voter_external_ids": [existing["external_id"]]},
        )
        assert seeded.status_code == 200, seeded.text
        events_before = len(eligibility_details(draft["id"]))

        # A good id followed by an unknown one, alongside a title change: none of it
        # may land - not the title, not the addition, not the removal of `existing`.
        response = put_election(
            organizer_token,
            draft["id"],
            {
                "title": "Should Not Persist",
                "eligible_voter_external_ids": [good["external_id"], "NON_EXISTING_XYZ"],
            },
        )
        assert response.status_code == 404

        fresh = get_election(organizer_token, draft["id"])
        assert fresh["title"] == original_title
        assert voter_external_ids(organizer_token, draft["id"]) == {existing["external_id"]}
        assert len(eligibility_details(draft["id"])) == events_before

    def test_duplicate_external_ids_are_rejected(self, organizer_token):
        voter = register_user("voter")
        draft = create_election_as_organizer(organizer_token)

        response = put_election(
            organizer_token,
            draft["id"],
            {"eligible_voter_external_ids": [voter["external_id"], voter["external_id"]]},
        )
        assert response.status_code == 400
        assert "duplicate" in response.json()["detail"].lower()
        assert voter_external_ids(organizer_token, draft["id"]) == set()

    def test_non_voter_account_is_rejected_on_a_draft(self, organizer_token):
        organizer = register_user("organizer")
        draft = create_election_as_organizer(organizer_token)

        response = put_election(
            organizer_token,
            draft["id"],
            {"eligible_voter_external_ids": [organizer["external_id"]]},
        )
        assert response.status_code == 400
        assert "voter" in response.json()["detail"].lower()

    def test_publishing_a_draft_preserves_its_id_and_activates_it(self, organizer_token):
        voter = register_user("voter")
        draft = create_election_as_organizer(organizer_token)
        drafts_before = draft_ids(organizer_token)

        saved = put_election(
            organizer_token,
            draft["id"],
            {
                "title": "Published Election",
                "eligible_voter_external_ids": [voter["external_id"]],
            },
        )
        assert saved.status_code == 200, saved.text

        activated = client.patch(
            f"{ELECTION_BASE}/{draft['id']}/activate",
            headers=auth_header(organizer_token),
        )
        assert activated.status_code == 200, activated.text

        data = activated.json()
        assert data["id"] == draft["id"]
        assert data["status"] == "active"
        assert data["title"] == "Published Election"

        # The draft was promoted, not copied: it leaves the draft list and no second
        # election takes its place.
        remaining = draft_ids(organizer_token)
        assert draft["id"] not in remaining
        assert len(remaining) == len(drafts_before) - 1

    def test_failed_activation_leaves_a_recoverable_draft(self, organizer_token):
        voter = register_user("voter")

        payload = valid_election_payload()
        payload["end_date"] = None  # no deadline: activation must refuse
        created = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )
        assert created.status_code == 201, created.text
        draft = created.json()

        saved = put_election(
            organizer_token,
            draft["id"],
            {
                "title": "Awaiting A Deadline",
                "eligible_voter_external_ids": [voter["external_id"]],
            },
        )
        assert saved.status_code == 200, saved.text

        activated = client.patch(
            f"{ELECTION_BASE}/{draft['id']}/activate",
            headers=auth_header(organizer_token),
        )
        assert activated.status_code == 400
        assert "deadline" in activated.json()["detail"].lower()

        # The edits survive, so the organizer can add a deadline and publish again.
        fresh = get_election(organizer_token, draft["id"])
        assert fresh["status"] == "draft"
        assert fresh["title"] == "Awaiting A Deadline"
        assert voter_external_ids(organizer_token, draft["id"]) == {voter["external_id"]}
        assert draft["id"] in draft_ids(organizer_token)

    def test_direct_active_creation_is_unchanged(self, organizer_token):
        voter = register_user("voter")

        payload = valid_election_payload()
        payload["eligible_voter_external_ids"] = [voter["external_id"]]

        response = client.post(ELECTION_BASE, json=payload, headers=auth_header(organizer_token))
        assert response.status_code == 201, response.text

        data = response.json()
        assert data["status"] == "active"
        assert len(data["candidates"]) == 2
        assert voter_external_ids(organizer_token, data["id"]) == {voter["external_id"]}
        # Direct creation never leaves a draft behind.
        assert data["id"] not in draft_ids(organizer_token)


def update_events(election_id: str) -> str:
    """The details of every election_updated event for an election, joined.

    The route records only the *names* of the fields that genuinely changed, so this
    is how a test asserts that something was â€” or was not â€” treated as a change.
    """
    from app.models.audit_log import AuditLog

    db = SessionLocal()
    try:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "election_updated",
                AuditLog.entity_id == UUID(election_id),
            )
            .all()
        )
        return " ".join(row.details or "" for row in rows)
    finally:
        db.close()


class TestDraftSnapshotUpdate:
    """PUT /elections/{id} must treat a draft as a snapshot of the form that saved it.

    An omitted field means "leave it alone"; an explicitly submitted value - including
    null and the empty list - means "make it so". Those two are different requests and
    the route has to tell them apart.
    """

    def test_explicit_null_end_date_clears_a_saved_deadline(self, organizer_token):
        draft = create_election_as_organizer(organizer_token)
        assert draft["end_date"] is not None

        response = put_election(organizer_token, draft["id"], {"end_date": None})
        assert response.status_code == 200, response.text
        assert response.json()["end_date"] is None

        fresh = get_election(organizer_token, draft["id"])
        assert fresh["end_date"] is None
        # A draft without a deadline simply cannot be published yet.
        activated = client.patch(
            f"{ELECTION_BASE}/{draft['id']}/activate",
            headers=auth_header(organizer_token),
        )
        assert activated.status_code == 400
        assert "deadline" in activated.json()["detail"].lower()

    def test_omitted_end_date_leaves_the_deadline_alone(self, organizer_token):
        draft = create_election_as_organizer(organizer_token)
        original_end_date = draft["end_date"]

        response = put_election(organizer_token, draft["id"], {"title": "Title Only"})
        assert response.status_code == 200, response.text
        assert response.json()["end_date"] == original_end_date

        fresh = get_election(organizer_token, draft["id"])
        assert fresh["end_date"] == original_end_date

    def test_clearing_the_deadline_is_recorded_once_and_is_idempotent(self, organizer_token):
        draft = create_election_as_organizer(organizer_token)

        first = put_election(organizer_token, draft["id"], {"end_date": None})
        assert first.status_code == 200, first.text

        # Re-submitting null against an already-null deadline is a no-op, so it must
        # not be logged as another change.
        second = put_election(organizer_token, draft["id"], {"end_date": None})
        assert second.status_code == 200, second.text
        assert second.json()["end_date"] is None

        assert update_events(draft["id"]).count("end_date") == 1

    def test_candidates_can_be_cleared_on_an_existing_draft(self, organizer_token):
        draft = create_election_as_organizer(organizer_token)
        assert len(draft["candidates"]) == 2

        response = put_election(organizer_token, draft["id"], {"candidates": []})
        assert response.status_code == 200, response.text
        assert response.json()["candidates"] == []

        fresh = get_election(organizer_token, draft["id"])
        assert fresh["candidates"] == []
        # Same relaxation the draft-create route grants, and activation still refuses.
        activated = client.patch(
            f"{ELECTION_BASE}/{draft['id']}/activate",
            headers=auth_header(organizer_token),
        )
        assert activated.status_code == 400
        assert "candidate" in activated.json()["detail"].lower()

    def test_cleared_candidates_can_be_retyped_on_the_same_draft(self, organizer_token):
        draft = create_election_as_organizer(organizer_token)

        cleared = put_election(organizer_token, draft["id"], {"candidates": []})
        assert cleared.status_code == 200, cleared.text

        retyped = put_election(
            organizer_token,
            draft["id"],
            {"candidates": [{"name": "Dana"}, {"name": "Eli"}]},
        )
        assert retyped.status_code == 200, retyped.text

        data = retyped.json()
        assert data["id"] == draft["id"]
        assert [c["name"] for c in data["candidates"]] == ["Dana", "Eli"]

    def test_omitted_start_date_is_never_moved(self, organizer_token):
        draft = create_election_as_organizer(organizer_token)
        original_start_date = draft["start_date"]

        response = put_election(
            organizer_token,
            draft["id"],
            {"title": "Renamed", "candidates": [{"name": "Dana"}]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["start_date"] == original_start_date

        fresh = get_election(organizer_token, draft["id"])
        assert fresh["start_date"] == original_start_date
        assert "start_date" not in update_events(draft["id"])

    def test_update_rejects_deadline_before_stored_start_date(self, organizer_token):
        draft = create_election_as_organizer(organizer_token)
        original_end_date = draft["end_date"]
        stored_start = datetime.fromisoformat(draft["start_date"])

        response = put_election(
            organizer_token,
            draft["id"],
            {"end_date": (stored_start - timedelta(minutes=1)).isoformat()},
        )

        assert response.status_code == 400
        assert "after start date" in response.json()["detail"].lower()
        fresh = get_election(organizer_token, draft["id"])
        assert fresh["end_date"] == original_end_date

    def test_activation_rejects_draft_with_deadline_before_start_date(
        self,
        organizer_token,
    ):
        voter = register_user("voter")
        payload = valid_election_payload()
        stored_start = datetime.fromisoformat(payload["start_date"])
        payload["end_date"] = (stored_start - timedelta(minutes=1)).isoformat()
        payload["eligible_voter_external_ids"] = [voter["external_id"]]

        created = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )
        assert created.status_code == 201, created.text
        draft = created.json()

        response = client.patch(
            f"{ELECTION_BASE}/{draft['id']}/activate",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "after start date" in response.json()["detail"].lower()
        fresh = get_election(organizer_token, draft["id"])
        assert fresh["status"] == "draft"

    def test_candidate_metadata_survives_a_resubmitted_name(self, organizer_token):
        """A payload that re-sends a candidate's stored description keeps it, and the
        no-op is not recorded as a change."""
        payload = valid_election_payload()
        created = client.post(
            f"{ELECTION_BASE}/draft",
            json=payload,
            headers=auth_header(organizer_token),
        )
        assert created.status_code == 201, created.text
        draft = created.json()
        stored = draft["candidates"][0]
        assert stored["description"] == "Candidate A"

        response = put_election(
            organizer_token,
            draft["id"],
            {
                "candidates": [
                    {
                        "name": c["name"],
                        "description": c["description"],
                        "photo_url": c["photo_url"],
                        "display_order": c["display_order"],
                    }
                    for c in draft["candidates"]
                ]
            },
        )
        assert response.status_code == 200, response.text

        fresh = get_election(organizer_token, draft["id"])
        assert fresh["candidates"][0]["description"] == "Candidate A"
        assert "candidates" not in update_events(draft["id"])

    def test_update_then_activate_keeps_one_election_on_the_same_id(self, organizer_token):
        """The publish path end to end: save the latest state, then activate that row."""
        voter = register_user("voter")
        draft = create_election_as_organizer(organizer_token)

        saved = put_election(
            organizer_token,
            draft["id"],
            {
                "title": "Final Title",
                "candidates": [{"name": "Dana"}, {"name": "Eli"}],
                "eligible_voter_external_ids": [voter["external_id"]],
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["id"] == draft["id"]

        activated = client.patch(
            f"{ELECTION_BASE}/{draft['id']}/activate",
            headers=auth_header(organizer_token),
        )
        assert activated.status_code == 200, activated.text

        data = activated.json()
        assert data["id"] == draft["id"]
        assert data["status"] == "active"
        # The saved edits are what got published.
        assert data["title"] == "Final Title"
        assert [c["name"] for c in data["candidates"]] == ["Dana", "Eli"]

        # Exactly one election carries this id, and nothing new appeared beside it.
        db = SessionLocal()
        try:
            rows = (
                db.query(Election)
                .filter(Election.organizer_id == UUID(activated.json()["organizer_id"]))
                .all()
            )
            assert len(rows) == 1
            assert str(rows[0].id) == draft["id"]
        finally:
            db.close()
