from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from tests.factories import provision_from_payload
from app.models.election import Election, ElectionStatus
from app.models.candidate_result import CandidateResult
from app.models.audit_log import AuditLog
from app.models.ballot import Ballot


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
def organizer_user():
    return register_user("organizer")


@pytest.fixture
def organizer_token(organizer_user):
    return login_user(organizer_user["email"])


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


def close_election(organizer_token: str, election_id: str):
    """Close an active election through the API. This is what runs the tally and
    caches candidate_results, so tests that need published results go through here
    rather than flipping the status directly."""
    response = client.post(
        f"{ELECTION_BASE}/{election_id}/close",
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def prepare_completed_election_with_vote(organizer_token, voter_user, voter_token):
    election = create_election_as_organizer(organizer_token)
    add_voter_to_election(organizer_token, election["id"], voter_user)
    activate_election(organizer_token, election["id"])

    candidate_id = election["candidates"][0]["id"]

    vote_response = client.post(
        VOTE_BASE,
        json={
            "election_id": election["id"],
            "candidate_id": candidate_id,
        },
        headers=auth_header(voter_token),
    )

    assert vote_response.status_code == 201, vote_response.text

    close_election(organizer_token, election["id"])

    return election, candidate_id


def three_candidate_election_payload() -> dict:
    now = datetime.utcnow()

    return {
        "title": unique_text("Multi Voter Tally Election"),
        "description": "Three-candidate election for tally characterization",
        "start_date": (now - timedelta(minutes=10)).isoformat(),
        "end_date": (now + timedelta(hours=24)).isoformat(),
        "candidates": [
            {"name": unique_text("Alice"), "description": "Candidate A", "photo_url": None, "display_order": 1},
            {"name": unique_text("Bob"), "description": "Candidate B", "photo_url": None, "display_order": 2},
            {"name": unique_text("Carol"), "description": "Candidate C", "photo_url": None, "display_order": 3},
        ],
    }


def create_three_candidate_election(organizer_token: str) -> dict:
    response = client.post(
        f"{ELECTION_BASE}/draft",
        json=three_candidate_election_payload(),
        headers=auth_header(organizer_token),
    )

    assert response.status_code == 201, response.text
    return response.json()


def cast_vote(voter_token: str, election_id: str, candidate_id: str):
    response = client.post(
        VOTE_BASE,
        json={"election_id": election_id, "candidate_id": candidate_id},
        headers=auth_header(voter_token),
    )

    assert response.status_code == 201, response.text
    return response.json()


class TestElectionResults:
    def test_organizer_can_view_completed_election_results(
        self,
        organizer_token,
        voter_user,
        voter_token,
    ):
        election, voted_candidate_id = prepare_completed_election_with_vote(
            organizer_token,
            voter_user,
            voter_token,
        )

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
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

    def test_voter_can_view_completed_election_results(
        self,
        organizer_token,
        voter_user,
        voter_token,
    ):
        election, _ = prepare_completed_election_with_vote(
            organizer_token,
            voter_user,
            voter_token,
        )

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["election_id"] == election["id"]

    def test_results_not_available_for_active_election(
        self,
        organizer_token,
        voter_user,
        voter_token,
    ):
        election = create_election_as_organizer(organizer_token)
        add_voter_to_election(organizer_token, election["id"], voter_user)
        set_election_status(election["id"], ElectionStatus.active)

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "progress" in response.json()["detail"].lower() or "completed" in response.json()["detail"].lower()

    def test_organizer_cannot_view_other_organizers_results(
        self,
        organizer_token,
        second_organizer_token,
        voter_user,
        voter_token,
    ):
        election, _ = prepare_completed_election_with_vote(
            organizer_token,
            voter_user,
            voter_token,
        )

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(second_organizer_token),
        )

        assert response.status_code == 403

    def test_missing_election_results_return_404(self, organizer_token):
        fake_id = uuid4()

        response = client.get(
            f"{RESULT_BASE}/elections/{fake_id}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 404

    def test_ineligible_voter_cannot_view_results(
        self,
        organizer_token,
        voter_user,
        voter_token,
    ):
        election, _ = prepare_completed_election_with_vote(
            organizer_token,
            voter_user,
            voter_token,
        )

        outsider = register_user("voter")
        outsider_token = login_user(outsider["email"])

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(outsider_token),
        )

        assert response.status_code == 403

    def test_draft_past_end_date_has_no_results(self, organizer_token):
        election = create_election_as_organizer(organizer_token)

        db = SessionLocal()
        try:
            row = db.query(Election).filter(Election.id == UUID(election["id"])).first()
            row.end_date = datetime.utcnow() - timedelta(days=1)
            db.commit()
        finally:
            db.close()

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400

    def test_tie_reports_no_single_winner(self, organizer_token, voter_user, voter_token):
        election = create_election_as_organizer(organizer_token)

        second_voter = register_user("voter")
        second_voter_token = login_user(second_voter["email"])

        add_voter_to_election(organizer_token, election["id"], voter_user)
        add_voter_to_election(organizer_token, election["id"], second_voter)
        activate_election(organizer_token, election["id"])

        candidate_one = election["candidates"][0]["id"]
        candidate_two = election["candidates"][1]["id"]

        first_vote = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_one},
            headers=auth_header(voter_token),
        )
        assert first_vote.status_code == 201, first_vote.text

        second_vote = client.post(
            VOTE_BASE,
            json={"election_id": election["id"], "candidate_id": candidate_two},
            headers=auth_header(second_voter_token),
        )
        assert second_vote.status_code == 201, second_vote.text

        close_election(organizer_token, election["id"])

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["winner"] is None
        assert len(data["tied_candidates"]) == 2

    def test_multi_voter_tally_maps_all_candidate_totals(self, organizer_token):
        """Known-answer characterization of the tally: four ballots cast across
        three candidates (two for A, one for B, one for C) must resolve to totals
        of 2, 1, and 1, with a reported total of 4 votes.

        This is deterministic — each of the four distinct voters casts exactly one
        ballot for a fixed candidate — and is self-contained: it creates its own
        organizer, voters, election, candidates, and ballots, all using @test.com
        users so the conftest cleanup fixture reclaims them afterwards.
        """
        election = create_three_candidate_election(organizer_token)

        candidate_a = election["candidates"][0]["id"]
        candidate_b = election["candidates"][1]["id"]
        candidate_c = election["candidates"][2]["id"]

        # Four distinct eligible voters, added while the election is still a draft.
        voter_tokens = []
        for _ in range(4):
            voter = register_user("voter")
            voter_tokens.append(login_user(voter["email"]))
            add_voter_to_election(organizer_token, election["id"], voter)

        # Activation generates the Paillier keypair used to encrypt the ballots.
        activate_election(organizer_token, election["id"])

        # Two votes for A, one for B, one for C.
        cast_vote(voter_tokens[0], election["id"], candidate_a)
        cast_vote(voter_tokens[1], election["id"], candidate_a)
        cast_vote(voter_tokens[2], election["id"], candidate_b)
        cast_vote(voter_tokens[3], election["id"], candidate_c)

        close_election(organizer_token, election["id"])

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        data = response.json()

        results_by_candidate = {
            item["candidate_id"]: item["total_votes"] for item in data["results"]
        }

        assert results_by_candidate == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }
        assert data["total_votes"] == 4


def build_active_election_with_voters(organizer_token: str, num_voters: int):
    """Create a three-candidate election through the API (draft → add voters →
    activate) so it has a real keystore entry, and return (election, voter_tokens)."""
    election = create_three_candidate_election(organizer_token)

    voter_tokens = []
    for _ in range(num_voters):
        voter = register_user("voter")
        voter_tokens.append(login_user(voter["email"]))
        add_voter_to_election(organizer_token, election["id"], voter)

    activate_election(organizer_token, election["id"])
    return election, voter_tokens


def cast_two_one_one(election: dict, voter_tokens: list) -> tuple:
    """Cast the known-answer ballots: 2 for candidate A, 1 for B, 1 for C.
    Requires exactly four voter tokens. Returns the three candidate ids."""
    candidate_a = election["candidates"][0]["id"]
    candidate_b = election["candidates"][1]["id"]
    candidate_c = election["candidates"][2]["id"]

    cast_vote(voter_tokens[0], election["id"], candidate_a)
    cast_vote(voter_tokens[1], election["id"], candidate_a)
    cast_vote(voter_tokens[2], election["id"], candidate_b)
    cast_vote(voter_tokens[3], election["id"], candidate_c)

    return candidate_a, candidate_b, candidate_c


def count_result_rows(election_id: str) -> int:
    db = SessionLocal()
    try:
        return (
            db.query(CandidateResult)
            .filter(CandidateResult.election_id == UUID(election_id))
            .count()
        )
    finally:
        db.close()


def stored_result_map(election_id: str) -> dict:
    db = SessionLocal()
    try:
        rows = (
            db.query(CandidateResult)
            .filter(CandidateResult.election_id == UUID(election_id))
            .all()
        )
        return {str(row.candidate_id): row.total_votes for row in rows}
    finally:
        db.close()


class TestCloseElection:
    def test_organizer_can_close_active_election_and_persist_tally(self, organizer_token):
        """Organizer closes an active election; the known-answer tally (2, 1, 1)
        is computed once and persisted as candidate_results, total 4."""
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "completed"

        stored = stored_result_map(election["id"])
        assert stored == {candidate_a: 2, candidate_b: 1, candidate_c: 1}
        assert sum(stored.values()) == 4

    def test_get_results_after_close_returns_cached_results(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)
        close_election(organizer_token, election["id"])

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        data = response.json()

        results_by_candidate = {
            item["candidate_id"]: item["total_votes"] for item in data["results"]
        }
        assert results_by_candidate == {candidate_a: 2, candidate_b: 1, candidate_c: 1}
        assert data["total_votes"] == 4

    def test_repeated_get_results_is_stable_and_writes_nothing(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)
        close_election(organizer_token, election["id"])

        first = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert first.status_code == 200, first.text
        rows_before = count_result_rows(election["id"])

        second = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert second.status_code == 200, second.text
        rows_after = count_result_rows(election["id"])

        # Identical payloads and no new/changed rows — the read did not re-tally.
        assert first.json() == second.json()
        assert rows_before == rows_after == 3

    def test_get_results_does_not_load_private_key(self, organizer_token, monkeypatch):
        """After close, reading results must never touch the keystore. Poison
        load_private_key so any call would fail, then prove GET still succeeds."""
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)
        close_election(organizer_token, election["id"])

        import app.security.keystore as keystore_module

        def _forbidden(*args, **kwargs):
            raise AssertionError("GET results must not load the private key")

        monkeypatch.setattr(keystore_module, "load_private_key", _forbidden)

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["total_votes"] == 4

    def test_second_close_is_rejected_and_does_not_duplicate_results(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)
        close_election(organizer_token, election["id"])

        rows_after_first = count_result_rows(election["id"])

        second = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=auth_header(organizer_token),
        )
        assert second.status_code == 400
        assert "active" in second.json()["detail"].lower()

        rows_after_second = count_result_rows(election["id"])
        assert rows_after_first == rows_after_second == 3
        assert stored_result_map(election["id"]) == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }

    def test_non_owner_organizer_cannot_close(self, organizer_token, second_organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=auth_header(second_organizer_token),
        )

        assert response.status_code == 403
        # No results were produced by the rejected close.
        assert count_result_rows(election["id"]) == 0

    def test_voter_cannot_close(self, organizer_token, voter_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=auth_header(voter_token),
        )

        assert response.status_code == 403
        assert count_result_rows(election["id"]) == 0

    def test_draft_election_cannot_be_closed(self, organizer_token):
        election = create_three_candidate_election(organizer_token)  # never activated

        response = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "active" in response.json()["detail"].lower()
        assert count_result_rows(election["id"]) == 0

    def test_close_records_audit_events_without_voter_choice(
        self, organizer_user, organizer_token
    ):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)
        close_election(organizer_token, election["id"])

        db = SessionLocal()
        try:
            rows = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == UUID(election["id"]))
                .all()
            )
            actions = {row.action for row in rows}
            assert "election_closed" in actions
            assert "results_published" in actions

            candidate_ids = {candidate["id"] for candidate in election["candidates"]}
            for row in rows:
                assert row.actor_user_id == UUID(organizer_user["id"])
                # The audit trail records THAT results were published, never a choice.
                for candidate_id in candidate_ids:
                    assert candidate_id not in (row.details or "")
        finally:
            db.close()


def complete_election(organizer_token: str, election_id: str):
    """Hit the legacy PATCH /complete endpoint (now routed through the same shared
    close/tally service as POST /close). Returns the raw response for the caller to
    assert on."""
    return client.patch(
        f"{ELECTION_BASE}/{election_id}/complete",
        headers=auth_header(organizer_token),
    )


class TestLegacyCompleteEndpoint:
    """The legacy PATCH /{id}/complete endpoint must never mark an election completed
    without producing cached results, and must be mutually exclusive with close so the
    tally can only ever run once."""

    def test_complete_runs_tally_and_caches_results(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)

        response = complete_election(organizer_token, election["id"])
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "completed"

        # The completion path tallied and cached results rather than leaving them empty.
        assert stored_result_map(election["id"]) == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }

        get_response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert get_response.status_code == 200, get_response.text
        data = get_response.json()
        results_by_candidate = {
            item["candidate_id"]: item["total_votes"] for item in data["results"]
        }
        assert results_by_candidate == {candidate_a: 2, candidate_b: 1, candidate_c: 1}
        assert data["total_votes"] == 4

    def test_completed_via_complete_never_lacks_cached_results(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)

        # Nothing is cached until the election is finalized.
        assert count_result_rows(election["id"]) == 0

        response = complete_election(organizer_token, election["id"])
        assert response.status_code == 200, response.text

        # A completed election always has one cached row per candidate.
        assert count_result_rows(election["id"]) == len(election["candidates"]) == 3

    def test_close_then_complete_is_rejected_without_duplicating(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)

        close_election(organizer_token, election["id"])
        rows_after_close = count_result_rows(election["id"])

        second = complete_election(organizer_token, election["id"])
        assert second.status_code == 400
        assert "active" in second.json()["detail"].lower()

        # The rejected complete neither re-tallied nor duplicated rows.
        assert count_result_rows(election["id"]) == rows_after_close == 3
        assert stored_result_map(election["id"]) == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }

    def test_complete_then_close_is_rejected_without_duplicating(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)

        completed = complete_election(organizer_token, election["id"])
        assert completed.status_code == 200, completed.text
        rows_after_complete = count_result_rows(election["id"])

        second = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=auth_header(organizer_token),
        )
        assert second.status_code == 400
        assert "active" in second.json()["detail"].lower()

        assert count_result_rows(election["id"]) == rows_after_complete == 3
        assert stored_result_map(election["id"]) == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }

    def test_non_owner_organizer_cannot_complete(self, organizer_token, second_organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)

        response = complete_election(second_organizer_token, election["id"])
        assert response.status_code == 403
        assert count_result_rows(election["id"]) == 0

    def test_voter_cannot_complete(self, organizer_token, voter_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)

        response = complete_election(voter_token, election["id"])
        assert response.status_code == 403
        assert count_result_rows(election["id"]) == 0


def multi_ballot_election_payload(num_candidates: int = 3, max_selections: int = 2) -> dict:
    now = datetime.utcnow()
    return {
        "title": unique_text("Multi Ballot Results Election"),
        "description": "multi-select results characterization",
        "start_date": (now - timedelta(minutes=10)).isoformat(),
        "end_date": (now + timedelta(hours=24)).isoformat(),
        "candidates": [
            {"name": unique_text(f"Cand{i}"), "description": f"C{i}", "photo_url": None, "display_order": i + 1}
            for i in range(num_candidates)
        ],
        "ballot_type": "multi",
        "max_selections": max_selections,
    }


def create_multi_ballot_election(organizer_token: str, num_candidates: int = 3, max_selections: int = 2) -> dict:
    response = client.post(
        f"{ELECTION_BASE}/draft",
        json=multi_ballot_election_payload(num_candidates, max_selections),
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit_selection(voter_token: str, election_id: str, candidate_ids: list):
    return client.post(
        VOTE_BASE,
        json={"election_id": election_id, "candidate_ids": candidate_ids},
        headers=auth_header(voter_token),
    )


def register_and_add_voters(organizer_token: str, election_id: str, count: int) -> list:
    tokens = []
    for _ in range(count):
        voter = register_user("voter")
        tokens.append(login_user(voter["email"]))
        add_voter_to_election(organizer_token, election_id, voter)
    return tokens


class TestMultiSelectAbstentionResults:
    def test_multi_select_known_tally_and_turnout(self, organizer_token):
        """Candidate totals count each selection; turnout counts ballots. With a
        multi-select ballot and an abstention the two diverge."""
        election = create_multi_ballot_election(organizer_token, num_candidates=3, max_selections=2)
        a, b, c = [cand["id"] for cand in election["candidates"]]

        tokens = register_and_add_voters(organizer_token, election["id"], 3)
        activate_election(organizer_token, election["id"])

        assert submit_selection(tokens[0], election["id"], [a, b]).status_code == 201  # 2 selections
        assert submit_selection(tokens[1], election["id"], [a, c]).status_code == 201  # 2 selections
        assert submit_selection(tokens[2], election["id"], []).status_code == 201       # abstention

        close_election(organizer_token, election["id"])

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text
        data = response.json()

        results_by_candidate = {item["candidate_id"]: item["total_votes"] for item in data["results"]}
        assert results_by_candidate == {a: 2, b: 1, c: 1}
        # Turnout is 3 ballots cast — NOT the sum of candidate totals (4).
        assert data["total_votes"] == 3
        assert sum(results_by_candidate.values()) == 4

    def test_all_abstentions_count_as_turnout_with_zero_candidate_totals(self, organizer_token):
        election = create_multi_ballot_election(organizer_token, num_candidates=3, max_selections=2)
        a, b, c = [cand["id"] for cand in election["candidates"]]

        tokens = register_and_add_voters(organizer_token, election["id"], 2)
        activate_election(organizer_token, election["id"])

        for token in tokens:
            assert submit_selection(token, election["id"], []).status_code == 201

        close_election(organizer_token, election["id"])

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["total_votes"] == 2  # turnout
        assert {item["candidate_id"]: item["total_votes"] for item in data["results"]} == {a: 0, b: 0, c: 0}
        assert data["winner"] is None
        assert data["tied_candidates"] == []

    def test_abstention_stored_as_real_encrypted_zero_vector(self, organizer_token):
        import json

        election = create_multi_ballot_election(organizer_token, num_candidates=3, max_selections=2)
        candidate_ids = [cand["id"] for cand in election["candidates"]]

        tokens = register_and_add_voters(organizer_token, election["id"], 1)
        activate_election(organizer_token, election["id"])
        assert submit_selection(tokens[0], election["id"], []).status_code == 201

        db = SessionLocal()
        try:
            ballot = db.query(Ballot).filter(Ballot.election_id == UUID(election["id"])).first()
            assert ballot is not None
            parsed = json.loads(ballot.encrypted_vote)
            # All candidates present; each entry is a real Paillier ciphertext, not "0".
            assert set(parsed.keys()) == set(candidate_ids)
            for entry in parsed.values():
                assert entry["c"] != "0"
                assert len(entry["c"]) > 10
        finally:
            db.close()

    def test_stored_multi_select_ballot_reveals_no_plaintext_selection(self, organizer_token):
        import json

        election = create_multi_ballot_election(organizer_token, num_candidates=3, max_selections=2)
        candidates = election["candidates"]
        selected = [candidates[0]["id"], candidates[1]["id"]]

        tokens = register_and_add_voters(organizer_token, election["id"], 1)
        activate_election(organizer_token, election["id"])
        assert submit_selection(tokens[0], election["id"], selected).status_code == 201

        db = SessionLocal()
        try:
            ballot = db.query(Ballot).filter(Ballot.election_id == UUID(election["id"])).first()
            assert ballot is not None

            # Candidate names never appear in plaintext.
            for cand in candidates:
                assert cand["name"] not in ballot.encrypted_vote
                assert cand["name"] not in ballot.ballot_commitment
                # The salted hash cannot encode/brute-force the choice.
                assert cand["id"] not in ballot.ballot_commitment

            # Every candidate is a key (multi-hot structure), so the key set does not
            # reveal which candidates were selected — the selection is only in the
            # encrypted values.
            parsed = json.loads(ballot.encrypted_vote)
            assert set(parsed.keys()) == {cand["id"] for cand in candidates}
        finally:
            db.close()

    def test_audit_log_hides_selections_and_abstention(self, organizer_token):
        election = create_multi_ballot_election(organizer_token, num_candidates=3, max_selections=2)
        candidates = election["candidates"]
        a, b = candidates[0]["id"], candidates[1]["id"]

        tokens = register_and_add_voters(organizer_token, election["id"], 2)
        activate_election(organizer_token, election["id"])
        assert submit_selection(tokens[0], election["id"], [a, b]).status_code == 201
        assert submit_selection(tokens[1], election["id"], []).status_code == 201  # abstention

        db = SessionLocal()
        try:
            rows = db.query(AuditLog).filter(AuditLog.action == "vote_cast").all()
            election_rows = [r for r in rows if f"election={election['id']}" in (r.details or "")]
            assert len(election_rows) == 2
            for row in election_rows:
                details = row.details or ""
                for cand in candidates:
                    assert cand["id"] not in details
                    assert cand["name"] not in details
                assert "abstain" not in details.lower()
        finally:
            db.close()

    def test_multi_close_tallies_once_and_repeated_get_is_stable(self, organizer_token):
        election = create_multi_ballot_election(organizer_token, num_candidates=3, max_selections=2)
        a, b, _c = [cand["id"] for cand in election["candidates"]]

        tokens = register_and_add_voters(organizer_token, election["id"], 2)
        activate_election(organizer_token, election["id"])
        assert submit_selection(tokens[0], election["id"], [a, b]).status_code == 201
        assert submit_selection(tokens[1], election["id"], []).status_code == 201  # abstention

        close_election(organizer_token, election["id"])
        rows_after_close = count_result_rows(election["id"])

        # Second close rejected — the tally runs exactly once, no duplicate rows.
        second = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=auth_header(organizer_token),
        )
        assert second.status_code == 400
        assert count_result_rows(election["id"]) == rows_after_close == 3

        # Repeated GET is stable and writes nothing.
        first_get = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        rows_before = count_result_rows(election["id"])
        second_get = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        rows_after = count_result_rows(election["id"])

        assert first_get.status_code == 200 and second_get.status_code == 200
        assert first_get.json() == second_get.json()
        assert rows_before == rows_after == 3
        # Turnout counts the multi ballot and the abstention as one each.
        assert first_get.json()["total_votes"] == 2


def expire_election(election_id: str):
    """Push an election's deadline into the past without touching its status."""
    db = SessionLocal()
    try:
        election = db.query(Election).filter(Election.id == UUID(election_id)).first()
        assert election is not None
        election.end_date = datetime.utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()


def election_status(election_id: str):
    db = SessionLocal()
    try:
        election = db.query(Election).filter(Election.id == UUID(election_id)).first()
        assert election is not None
        return election.status
    finally:
        db.close()


class TestAutoFinalizeExpiredElection:
    """An active election whose deadline has passed is finalized once, on demand,
    through the same locked close/tally workflow as the explicit close endpoints."""

    def test_expired_active_election_is_finalized_on_results_request(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)

        expire_election(election["id"])
        # Still active with nothing cached before the first read.
        assert election_status(election["id"]) == ElectionStatus.active
        assert count_result_rows(election["id"]) == 0

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "completed"
        assert {item["candidate_id"]: item["total_votes"] for item in data["results"]} == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }
        assert data["total_votes"] == 4

        # The tally was persisted, not merely computed for this response.
        assert election_status(election["id"]) == ElectionStatus.completed
        assert stored_result_map(election["id"]) == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }
        assert count_result_rows(election["id"]) == 3

    def test_repeated_requests_do_not_retally_or_duplicate_results(
        self, organizer_token, monkeypatch
    ):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)
        expire_election(election["id"])

        first = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert first.status_code == 200, first.text
        assert count_result_rows(election["id"]) == 3

        # Once finalized, a later read must never reach the tally again. Poison the
        # keystore lookup where the close workflow actually binds it.
        import app.routes.election_routes as election_routes_module

        def _forbidden(*args, **kwargs):
            raise AssertionError("a finalized election must not be re-tallied")

        monkeypatch.setattr(election_routes_module, "load_private_key", _forbidden)

        second = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert second.status_code == 200, second.text
        assert second.json() == first.json()
        assert count_result_rows(election["id"]) == 3

    def test_active_election_before_its_deadline_is_not_finalized(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)
        # The deadline is still in the future — results stay unavailable.

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert "progress" in response.json()["detail"].lower()
        assert election_status(election["id"]) == ElectionStatus.active
        assert count_result_rows(election["id"]) == 0

    def test_expired_draft_is_not_finalized(self, organizer_token):
        election = create_three_candidate_election(organizer_token)  # never activated
        expire_election(election["id"])

        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 400
        assert election_status(election["id"]) == ElectionStatus.draft
        assert count_result_rows(election["id"]) == 0

    def test_voter_reading_results_after_the_deadline_triggers_finalize(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)
        expire_election(election["id"])

        # An eligible voter — not the organizer — is the first to read the results.
        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(voter_tokens[0]),
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert {item["candidate_id"]: item["total_votes"] for item in data["results"]} == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }
        assert data["total_votes"] == 4
        assert election_status(election["id"]) == ElectionStatus.completed

    def test_auto_finalize_audits_the_close_as_the_organizer_with_a_deadline_reason(
        self, organizer_user, organizer_token
    ):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        cast_two_one_one(election, voter_tokens)
        expire_election(election["id"])

        # Triggered by a voter's read, but the close belongs to the organizer.
        response = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(voter_tokens[0]),
        )
        assert response.status_code == 200, response.text

        db = SessionLocal()
        try:
            rows = (
                db.query(AuditLog)
                .filter(AuditLog.entity_id == UUID(election["id"]))
                .all()
            )
            close_rows = [row for row in rows if row.action == "election_closed"]
            published_rows = [row for row in rows if row.action == "results_published"]

            # Exactly one close/publish pair — the tally ran once.
            assert len(close_rows) == 1
            assert len(published_rows) == 1

            for row in close_rows + published_rows:
                # A voter merely reading results is never recorded as the closer.
                assert row.actor_user_id == UUID(organizer_user["id"])
                assert "deadline" in (row.details or "")
                # The audit trail still never carries a ballot choice.
                for candidate in election["candidates"]:
                    assert candidate["id"] not in (row.details or "")
        finally:
            db.close()

    def test_explicit_close_after_auto_finalize_is_rejected(self, organizer_token):
        election, voter_tokens = build_active_election_with_voters(organizer_token, 4)
        candidate_a, candidate_b, candidate_c = cast_two_one_one(election, voter_tokens)
        expire_election(election["id"])

        first = client.get(
            f"{RESULT_BASE}/elections/{election['id']}",
            headers=auth_header(organizer_token),
        )
        assert first.status_code == 200, first.text

        # The election is already completed, so the manual close must refuse rather
        # than run a second tally or duplicate the cached rows.
        close_response = client.post(
            f"{ELECTION_BASE}/{election['id']}/close",
            headers=auth_header(organizer_token),
        )

        assert close_response.status_code == 400
        assert "active" in close_response.json()["detail"].lower()
        assert count_result_rows(election["id"]) == 3
        assert stored_result_map(election["id"]) == {
            candidate_a: 2,
            candidate_b: 1,
            candidate_c: 1,
        }