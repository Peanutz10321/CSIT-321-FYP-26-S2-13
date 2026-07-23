"""
Audit coverage for the admin and election-lifecycle workflows (PR 7).

These drive the real routes against the real database, so they assert what an
auditor would actually find afterwards: the event exists, it names the right
entity, it records safe old/new values, and it never carries an email, a
candidate name, or any ballot material.

The chain test at the bottom checks the segment these workflows produce rather
than the whole table: the suite's clean_test_records fixture deletes audit rows
between tests, so a whole-table verification here would fail on gaps that the
harness created, not the code. Whole-chain verification is covered against an
isolated database in tests/test_audit_chain.py.
"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.database import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.security.audit import compute_entry_hash
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
        assert row["details"] == "role=organizer"

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
        assert row["details"] == "old_status=active;new_status=inactive"

    def test_suspend_is_audited(self, admin_token):
        voter = register_voter()

        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/suspend", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text

        row = one_row("user_suspended", voter["id"])
        assert row["details"] == "old_status=active;new_status=suspended"

    def test_unsuspend_is_audited(self, admin_token):
        voter = register_voter()

        client.patch(f"{ADMIN_BASE}/{voter['id']}/suspend", headers=auth_header(admin_token))
        response = client.patch(
            f"{ADMIN_BASE}/{voter['id']}/unsuspend", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text

        row = one_row("user_unsuspended", voter["id"])
        assert row["details"] == "old_status=suspended;new_status=active"

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
        assert row["details"] == "status=draft"

    def test_active_creation_is_audited_without_duplicating_key_generation(
        self, organizer_token
    ):
        voter = register_voter()
        election = create_active(organizer_token, voter)

        row = one_row("election_created", election["id"])
        assert row["details"] == "status=active"

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
        assert row["details"] == "status=draft;fields=description"

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
        assert row["details"] == f"old_title={election['title']};new_title={new_title}"

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
        assert row["details"].startswith("old_end_date=")
        assert "new_end_date=" in row["details"]

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
        assert row["details"] == f"old_title={election['title']};new_title={new_title}"

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
        assert row["details"] == "status=draft"

        detail_response = client.get(
            f"{ELECTION_BASE}/{election['id']}", headers=auth_header(organizer_token)
        )
        assert detail_response.status_code == 404


# ---------------------------------------------------------------------------
# Chain integrity across a real workflow
# ---------------------------------------------------------------------------


def test_workflow_events_form_an_intact_chain_segment(organizer_token, admin_token):
    """Everything these workflows append must still hash and link correctly.

    Scoped to the entries this test produces, because the suite's cleanup fixture
    deletes rows between tests and would otherwise show as chain gaps.
    """
    baseline = max_sequence()

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

    segment = rows_after(baseline)
    assert len(segment) >= 5, [row["action"] for row in segment]

    # Contiguous positions.
    positions = [row["sequence_number"] for row in segment]
    assert positions == list(range(positions[0], positions[0] + len(positions)))

    for index, row in enumerate(segment):
        recomputed = compute_entry_hash(
            sequence_number=row["sequence_number"],
            previous_hash=row["previous_hash"],
            actor_user_id=row["actor_user_id"],
            action=row["action"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            details=row["details"],
            created_at=row["created_at"],
        )
        assert recomputed == row["entry_hash"], f"entry {row['sequence_number']} does not hash"

        if index > 0:
            assert row["previous_hash"] == segment[index - 1]["entry_hash"]
