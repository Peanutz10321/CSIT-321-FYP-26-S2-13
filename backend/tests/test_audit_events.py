"""
Audit coverage for the admin and election-lifecycle workflows (PR 7).

These drive the real routes against the real database, so they assert what an
auditor would actually find afterwards: the event exists, it names the right
entity, it records safe old/new values, and it never carries an email, a
candidate name, or any ballot material.

The chain test at the bottom checks the complete trail these workflows produce.
The SQLite test database is disposable, so ``clean_test_records`` resets both
``audit_logs`` and ``audit_chain_head`` together between tests. Every test starts
from genesis, allowing route-driven verification from the first row through the
current head without harness-created gaps.
"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.database import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.security.audit import audit_details, compute_entry_hash, verify_audit_chain
from tests.factories import create_system_admin, provision_from_payload


client = TestClient(app)

AUTH_BASE = "/auth"
ELECTION_BASE = "/elections"
ADMIN_BASE = "/admin/users"


def unique_text(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_voter() -> dict:
    suffix = uuid4().hex[:8]
    payload = {
        "role": "voter",
        "external_id": f"VOTER-{suffix}",
        "username": f"voter_{suffix}",
        "full_name": "Test Voter",
        "email": f"voter_{suffix}@test.com",
        "password": "testing123",
    }
    response = client.post(f"{AUTH_BASE}/register", json=payload)
    assert response.status_code in (200, 201), response.text
    return {**payload, **response.json()}


def provision_organizer() -> dict:
    suffix = uuid4().hex[:8]
    payload = {
        "role": "organizer",
        "external_id": f"ORG-{suffix}",
        "username": f"organizer_{suffix}",
        "full_name": "Test Organizer",
        "email": f"organizer_{suffix}@test.com",
        "password": "testing123",
    }
    return {**payload, **provision_from_payload(payload)}


def login(email: str, password: str = "testing123") -> str:
    response = client.post(
        f"{AUTH_BASE}/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def admin_token():
    admin = create_system_admin()
    return login(admin["email"])


@pytest.fixture
def organizer_token():
    return login(provision_organizer()["email"])


# ---------------------------------------------------------------------------
# Reading the trail back
# ---------------------------------------------------------------------------


def audit_rows(action=None, entity_id=None):
    """Audit rows as plain dicts, oldest first, detached from any session."""
    db = SessionLocal()
    try:
        query = db.query(AuditLog)
        if action is not None:
            query = query.filter(AuditLog.action == action)
        if entity_id is not None:
            query = query.filter(AuditLog.entity_id == UUID(str(entity_id)))

        return [
            {
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor_user_id": row.actor_user_id,
                # Kept raw: None and "" must not be conflated, or the hash
                # recomputation below would silently diverge from what was stored.
                "details": row.details,
                "sequence_number": row.sequence_number,
                "previous_hash": row.previous_hash,
                "entry_hash": row.entry_hash,
                "created_at": row.created_at,
            }
            for row in query.order_by(AuditLog.sequence_number).all()
        ]
    finally:
        db.close()


def one_row(action, entity_id):
    rows = audit_rows(action=action, entity_id=entity_id)
    assert len(rows) == 1, f"expected exactly one {action} row, got {len(rows)}"
    return rows[0]


def max_sequence() -> int:
    db = SessionLocal()
    try:
        return db.query(func.max(AuditLog.sequence_number)).scalar() or 0
    finally:
        db.close()


def rows_after(baseline: int):
    return [row for row in audit_rows() if row["sequence_number"] > baseline]


# ---------------------------------------------------------------------------
# Election helpers
# ---------------------------------------------------------------------------


def draft_payload() -> dict:
    now = datetime.utcnow()
    return {
        "title": unique_text("Draft Election"),
        "description": "Audit event coverage",
        "start_date": (now - timedelta(minutes=10)).isoformat(),
        "end_date": (now + timedelta(hours=24)).isoformat(),
        "candidates": [
            {"name": unique_text("Alice"), "display_order": 1},
            {"name": unique_text("Bob"), "display_order": 2},
        ],
    }


def create_draft(organizer_token: str) -> dict:
    response = client.post(
        f"{ELECTION_BASE}/draft",
        json=draft_payload(),
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_active(organizer_token: str, voter: dict) -> dict:
    payload = {**draft_payload(), "eligible_voter_external_ids": [voter["external_id"]]}
    response = client.post(
        f"{ELECTION_BASE}/",
        json=payload,
        headers=auth_header(organizer_token),
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Admin user workflows
# ---------------------------------------------------------------------------


class TestAdminUserEvents:
    def test_creating_an_organizer_is_audited(self, admin_token):
        suffix = uuid4().hex[:8]
        response = client.post(
            f"{ADMIN_BASE}/organizers",
            json={
                "username": f"new_org_{suffix}",
                "email": f"new_org_{suffix}@test.com",
                "password": "organizer-pass-123",
                "full_name": "Provisioned Organizer",
            },
            headers=auth_header(admin_token),
        )
        assert response.status_code == 201, response.text
        organizer = response.json()

        row = one_row("organizer_created", organizer["id"])
        assert row["entity_type"] == "user"
        assert row["details"] == '{"role":"organizer"}'

    def test_organizer_creation_audit_holds_no_credentials(self, admin_token):
        suffix = uuid4().hex[:8]
        email = f"secret_org_{suffix}@test.com"
        password = "organizer-pass-123"

        response = client.post(
            f"{ADMIN_BASE}/organizers",
            json={
                "username": f"secret_org_{suffix}",
                "email": email,
                "password": password,
                "full_name": "Provisioned Organizer",
            },
            headers=auth_header(admin_token),
        )
        assert response.status_code == 201, response.text

        details = one_row("organizer_created", response.json()["id"])["details"]
        assert email not in details
        assert password not in details
        assert f"secret_org_{suffix}" not in details

    def test_status_change_records_both_sides(self, admin_token):
        voter = register_voter()

        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/status",
            json={"status": "inactive"},
            headers=auth_header(admin_token),
        )
        assert response.status_code == 200, response.text

        row = one_row("user_status_changed", voter["id"])
        assert row["entity_type"] == "user"
        assert row["details"] == '{"new_status":"inactive","old_status":"active"}'

    def test_suspend_is_audited(self, admin_token):
        voter = register_voter()

        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/suspend", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text

        row = one_row("user_suspended", voter["id"])
        assert row["details"] == '{"new_status":"suspended","old_status":"active"}'

    def test_unsuspend_is_audited(self, admin_token):
        voter = register_voter()

        client.patch(f"{ADMIN_BASE}/{voter['id']}/suspend", headers=auth_header(admin_token))
        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/unsuspend", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text

        row = one_row("user_unsuspended", voter["id"])
        assert row["details"] == '{"new_status":"active","old_status":"suspended"}'

    def test_a_rejected_status_change_leaves_no_event(self, admin_token):
        """An admin cannot suspend themselves, and the refusal is not an event."""
        db = SessionLocal()
        try:
            before = db.query(AuditLog).filter(AuditLog.action == "user_suspended").count()
        finally:
            db.close()

        missing_user = uuid4()
        response = client.patch(
            f"{ADMIN_BASE}/{missing_user}/suspend", headers=auth_header(admin_token)
        )
        assert response.status_code == 404

        db = SessionLocal()
        try:
            after = db.query(AuditLog).filter(AuditLog.action == "user_suspended").count()
        finally:
            db.close()

        assert after == before


# ---------------------------------------------------------------------------
# Election lifecycle workflows
# ---------------------------------------------------------------------------


class TestElectionLifecycleEvents:
    def test_draft_creation_is_audited(self, organizer_token):
        election = create_draft(organizer_token)

        row = one_row("election_created", election["id"])
        assert row["entity_type"] == "election"
        assert row["details"] == '{"status":"draft"}'

    def test_active_creation_is_audited_without_duplicating_key_generation(
        self, organizer_token
    ):
        voter = register_voter()
        election = create_active(organizer_token, voter)

        row = one_row("election_created", election["id"])
        assert row["details"] == '{"status":"active"}'

        # The pre-existing events must still fire exactly once each.
        assert len(audit_rows("key_generated", election["id"])) == 1
        assert len(audit_rows("eligibility_changed", election["id"])) == 1

    def test_draft_update_records_the_changed_fields(self, organizer_token):
        election = create_draft(organizer_token)

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json={"description": "Revised description"},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        row = one_row("election_updated", election["id"])
        assert row["details"] == '{"fields":["description"],"status":"draft"}'

    def test_draft_update_does_not_record_candidate_names(self, organizer_token):
        election = create_draft(organizer_token)
        new_name = unique_text("Charlie")

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json={"candidates": [{"name": new_name, "display_order": 1}]},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        row = one_row("election_updated", election["id"])
        assert "candidates" in row["details"]
        assert new_name not in row["details"], "candidate names must never be audited"

    def test_renaming_a_draft_emits_a_title_event(self, organizer_token):
        election = create_draft(organizer_token)
        new_title = unique_text("Renamed Election")

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json={"title": new_title},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        row = one_row("election_title_changed", election["id"])
        assert row["details"] == audit_details(old_title=election["title"], new_title=new_title)

    def test_an_unchanged_title_emits_no_title_event(self, organizer_token):
        election = create_draft(organizer_token)

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json={"title": election["title"]},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        assert audit_rows("election_title_changed", election["id"]) == []

    def test_deadline_extension_records_both_dates(self, organizer_token):
        voter = register_voter()
        election = create_active(organizer_token, voter)
        new_end = datetime.utcnow() + timedelta(days=5)

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/extend-deadline",
            json={"new_end_date": new_end.isoformat()},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        row = one_row("election_deadline_extended", election["id"])
        assert '"old_end_date"' in row["details"]
        assert '"new_end_date"' in row["details"]

    def test_renaming_through_extend_deadline_emits_a_title_event(self, organizer_token):
        voter = register_voter()
        election = create_active(organizer_token, voter)
        new_title = unique_text("Active Renamed")
        new_end = datetime.utcnow() + timedelta(days=5)

        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/extend-deadline",
            json={"new_end_date": new_end.isoformat(), "title": new_title},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        row = one_row("election_title_changed", election["id"])
        assert row["details"] == audit_details(old_title=election["title"], new_title=new_title)

    def test_draft_deletion_is_audited_and_the_event_outlives_the_election(
        self, organizer_token
    ):
        election = create_draft(organizer_token)

        response = client.delete(
            f"{ELECTION_BASE}/{election['id']}", headers=auth_header(organizer_token)
        )
        assert response.status_code == 204, response.text

        # The election is gone; the audit row that records its deletion is not.
        row = one_row("election_deleted", election["id"])
        assert row["details"] == '{"status":"draft"}'

        detail_response = client.get(
            f"{ELECTION_BASE}/{election['id']}", headers=auth_header(organizer_token)
        )
        assert detail_response.status_code == 404


# ---------------------------------------------------------------------------
# Chain integrity across a real workflow
# ---------------------------------------------------------------------------


def test_route_driven_chain_verifies_from_genesis_to_head(organizer_token, admin_token):
    """The whole route-driven chain must verify, not merely a slice of it.

    The cleanup fixture now resets audit_logs and the chain head together, so each
    test starts from an intact chain at genesis. That lets this assert the real
    property — verify_audit_chain over the entire table passes — rather than the
    old segment-only check that stepped around a broken harness.
    """
    db = SessionLocal()
    try:
        # Precondition: the reset really did leave a clean chain to build on.
        assert verify_audit_chain(db).ok
        assert db.query(AuditLog).count() == 0
    finally:
        db.close()

    voter = register_voter()
    election = create_active(organizer_token, voter)

    client.patch(
        f"{ELECTION_BASE}/{election['id']}/extend-deadline",
        json={
            "new_end_date": (datetime.utcnow() + timedelta(days=3)).isoformat(),
            "title": unique_text("Renamed"),
        },
        headers=auth_header(organizer_token),
    )
    client.patch(f"{ADMIN_BASE}/{voter['id']}/suspend", headers=auth_header(admin_token))

    db = SessionLocal()
    try:
        result = verify_audit_chain(db)
        assert result.ok, [problem.message for problem in result.problems]
        rows = db.query(AuditLog).order_by(AuditLog.sequence_number).all()
        assert result.checked == len(rows) >= 5
        assert [row.sequence_number for row in rows] == list(range(1, len(rows) + 1))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Election activation (issue B) — both paths emit election_activated once
# ---------------------------------------------------------------------------


class TestActivationEvents:
    def test_direct_active_creation_emits_election_activated_once(self, organizer_token):
        voter = register_voter()
        election = create_active(organizer_token, voter)

        assert len(audit_rows("election_activated", election["id"])) == 1
        # key_generated fires exactly once — activation does not bring a second.
        assert len(audit_rows("key_generated", election["id"])) == 1

    def test_draft_activation_emits_election_activated_once(self, organizer_token):
        voter = register_voter()
        election = create_draft(organizer_token)
        client.post(
            f"{ELECTION_BASE}/{election['id']}/voters",
            json={"external_id": voter["external_id"]},
            headers=auth_header(organizer_token),
        )
        response = client.patch(
            f"{ELECTION_BASE}/{election['id']}/activate",
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        assert len(audit_rows("election_activated", election["id"])) == 1
        assert len(audit_rows("key_generated", election["id"])) == 1

    def test_direct_active_creation_orders_created_before_activated(self, organizer_token):
        voter = register_voter()
        election = create_active(organizer_token, voter)

        actions = [row["action"] for row in audit_rows(entity_id=election["id"])]

        assert actions.index("election_created") < actions.index("key_generated")
        assert actions.index("key_generated") < actions.index("election_activated")
        assert actions[-1] == "election_activated"


# ---------------------------------------------------------------------------
# No-op and consistency (issue C)
# ---------------------------------------------------------------------------


class TestNoOpStatusEvents:
    def test_resuspending_a_suspended_user_records_nothing(self, admin_token):
        voter = register_voter()
        client.patch(f"{ADMIN_BASE}/{voter['id']}/suspend", headers=auth_header(admin_token))

        before = len(audit_rows(entity_id=voter["id"]))
        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/suspend", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text

        assert len(audit_rows(entity_id=voter["id"])) == before

    def test_unsuspending_an_active_user_records_nothing(self, admin_token):
        voter = register_voter()  # already active

        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/unsuspend", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text

        assert audit_rows("user_unsuspended", voter["id"]) == []

    def test_generic_status_to_current_value_records_nothing(self, admin_token):
        voter = register_voter()  # active

        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/status",
            json={"status": "active"},
            headers=auth_header(admin_token),
        )
        assert response.status_code == 200, response.text

        assert audit_rows(entity_id=voter["id"]) == []

    def test_generic_status_to_suspended_is_classified_as_suspension(self, admin_token):
        """The generic route and the dedicated suspend route agree on semantics."""
        voter = register_voter()

        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/status",
            json={"status": "suspended"},
            headers=auth_header(admin_token),
        )
        assert response.status_code == 200, response.text

        assert len(audit_rows("user_suspended", voter["id"])) == 1
        assert audit_rows("user_status_changed", voter["id"]) == []

    def test_generic_status_out_of_suspended_is_classified_as_unsuspension(self, admin_token):
        voter = register_voter()
        client.patch(f"{ADMIN_BASE}/{voter['id']}/suspend", headers=auth_header(admin_token))

        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/status",
            json={"status": "active"},
            headers=auth_header(admin_token),
        )
        assert response.status_code == 200, response.text

        assert len(audit_rows("user_unsuspended", voter["id"])) == 1


class TestNoOpElectionUpdate:
    def test_update_with_no_changes_records_nothing(self, organizer_token):
        election = create_draft(organizer_token)

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json={"title": election["title"], "description": election["description"]},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        assert audit_rows("election_updated", election["id"]) == []
        assert audit_rows("election_title_changed", election["id"]) == []

    def test_update_records_only_the_genuinely_changed_fields(self, organizer_token):
        election = create_draft(organizer_token)

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            # title resubmitted unchanged; only description differs.
            json={"title": election["title"], "description": "A new description"},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        row = one_row("election_updated", election["id"])
        assert row["details"] == '{"fields":["description"],"status":"draft"}'
        assert audit_rows("election_title_changed", election["id"]) == []


# ---------------------------------------------------------------------------
# Structured details survive punctuation (issue D)
# ---------------------------------------------------------------------------


class TestDetailEncoding:
    def test_title_with_delimiters_stays_valid_json(self, organizer_token):
        """A title full of ; = " and newlines must not corrupt the details."""
        import json

        election = create_draft(organizer_token)
        nasty = 'a;b=c"d\n{}[]' + unique_text("")

        response = client.put(
            f"{ELECTION_BASE}/{election['id']}",
            json={"title": nasty},
            headers=auth_header(organizer_token),
        )
        assert response.status_code == 200, response.text

        row = one_row("election_title_changed", election["id"])
        parsed = json.loads(row["details"])  # must not raise
        assert parsed["new_title"] == nasty
        assert parsed["old_title"] == election["title"]


# ---------------------------------------------------------------------------
# Vote unlinkability (issue E)
# ---------------------------------------------------------------------------


class TestVoteAuditUnlinkability:
    def test_vote_cast_is_recorded_at_election_level(self, organizer_token):
        voter = register_voter()
        election = create_active(organizer_token, voter)
        token = login(voter["email"])

        response = client.post(
            "/votes/",
            json={
                "election_id": election["id"],
                "candidate_id": election["candidates"][0]["id"],
            },
            headers=auth_header(token),
        )
        assert response.status_code == 201, response.text
        ballot_id = response.json()["id"]
        receipt_code = response.json()["receipt_code"]

        row = one_row("vote_cast", election["id"])
        assert row["entity_type"] == "election"
        assert str(row["entity_id"]) == str(election["id"])

        # The whole point: no vote_cast audit row may carry the ballot id, or
        # audit_logs ⨝ ballots would restore the voter→ballot link.
        for vote_row in audit_rows("vote_cast"):
            assert str(vote_row["entity_id"]) != str(ballot_id)
            assert ballot_id not in (vote_row["details"] or "")
            assert receipt_code not in (vote_row["details"] or "")
