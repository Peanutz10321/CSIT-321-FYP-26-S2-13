"""
Tests for the hash-chained audit log (PR 6).

These run against their own throwaway in-memory database rather than the shared
test database. The suite's clean_test_records fixture deletes audit rows between
tests, which is exactly the "missing entry" condition verification is supposed to
report — so a chain test sharing that database would be meaningless. Here the
chain starts empty and nothing else writes to it.
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.models.audit_log import AuditChainHead, AuditLog
from app.models.user import User, UserRole, UserStatus
from app.security.audit import (
    CHAIN_ID,
    GENESIS_HASH,
    canonical_entry,
    compute_entry_hash,
    log_event,
    verify_audit_chain,
)


@pytest.fixture
def chain_db():
    """A private database containing nothing but this test's audit chain."""
    engine = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def actor(chain_db):
    user = User(
        external_id="AUDIT-001",
        username="audit_actor",
        full_name="Audit Actor",
        email="audit_actor@test.com",
        password_hash="not-a-real-hash",
        role=UserRole.voter,
        status=UserStatus.active,
    )
    chain_db.add(user)
    chain_db.commit()
    return user


def append(chain_db, actor, action="election_activated", **kwargs):
    """Log one event and commit it, the way a route would."""
    entry = log_event(
        chain_db,
        actor_user_id=actor.id,
        action=action,
        entity_type=kwargs.pop("entity_type", "election"),
        **kwargs,
    )
    chain_db.commit()
    return entry


def entries(chain_db):
    return chain_db.query(AuditLog).order_by(AuditLog.sequence_number).all()


def tamper(chain_db, sql, **params):
    """Edit rows behind the ORM's back, as a database-only attacker would."""
    chain_db.execute(sa.text(sql), params)
    chain_db.commit()
    chain_db.expire_all()


# ---------------------------------------------------------------------------
# Canonical serialisation
# ---------------------------------------------------------------------------


class TestCanonicalSerialisation:
    def base_fields(self):
        return {
            "sequence_number": 1,
            "previous_hash": GENESIS_HASH,
            "actor_user_id": "6f1a8f4e-6c4a-4f9e-9a0b-2f7c1d3e5a6b",
            "action": "vote_cast",
            "entity_type": "ballot",
            "entity_id": None,
            "details": "election=1",
            "created_at": None,
        }

    def test_serialisation_is_stable_and_sorted(self):
        text = canonical_entry(**self.base_fields())

        assert text == canonical_entry(**self.base_fields())
        # Sorted keys, no incidental whitespace.
        assert text.startswith('{"action":"vote_cast",')
        assert ", " not in text

    def test_uuid_spelling_does_not_change_the_hash(self):
        """A UUID object, a hyphenated string and a bare hex string are one id.

        PostgreSQL hands back UUID objects and SQLite hands back strings; the
        chain has to survive that difference.
        """
        import uuid

        raw = "6f1a8f4e-6c4a-4f9e-9a0b-2f7c1d3e5a6b"
        fields = self.base_fields()

        as_object = compute_entry_hash(**{**fields, "actor_user_id": uuid.UUID(raw)})
        as_hyphenated = compute_entry_hash(**{**fields, "actor_user_id": raw})
        as_bare_hex = compute_entry_hash(**{**fields, "actor_user_id": raw.replace("-", "")})

        assert as_object == as_hyphenated == as_bare_hex

    @pytest.mark.parametrize(
        "field, value",
        [
            ("sequence_number", 2),
            ("previous_hash", "f" * 64),
            ("action", "election_closed"),
            ("entity_type", "election"),
            ("details", "election=2"),
        ],
    )
    def test_changing_any_field_changes_the_hash(self, field, value):
        original = compute_entry_hash(**self.base_fields())

        assert compute_entry_hash(**{**self.base_fields(), field: value}) != original


# ---------------------------------------------------------------------------
# Appending
# ---------------------------------------------------------------------------


class TestSequentialInsertion:
    def test_entries_are_numbered_from_one_and_linked(self, chain_db, actor):
        first = append(chain_db, actor, action="key_generated")
        second = append(chain_db, actor, action="election_activated")
        third = append(chain_db, actor, action="election_closed")

        assert [e.sequence_number for e in (first, second, third)] == [1, 2, 3]
        assert first.previous_hash == GENESIS_HASH
        assert second.previous_hash == first.entry_hash
        assert third.previous_hash == second.entry_hash

    def test_several_events_in_one_transaction_get_distinct_positions(
        self, chain_db, actor
    ):
        """Closing an election logs two events before a single commit."""
        log_event(
            chain_db,
            actor_user_id=actor.id,
            action="election_closed",
            entity_type="election",
        )
        log_event(
            chain_db,
            actor_user_id=actor.id,
            action="results_published",
            entity_type="election",
        )
        chain_db.commit()

        rows = entries(chain_db)
        assert [row.sequence_number for row in rows] == [1, 2]
        assert rows[1].previous_hash == rows[0].entry_hash
        assert verify_audit_chain(chain_db).ok

    def test_chain_head_tracks_the_last_entry(self, chain_db, actor):
        append(chain_db, actor)
        last = append(chain_db, actor)

        head = chain_db.query(AuditChainHead).filter(AuditChainHead.id == CHAIN_ID).one()

        assert head.sequence_number == last.sequence_number
        assert head.head_hash == last.entry_hash

    def test_log_event_does_not_commit_by_itself(self, chain_db, actor):
        """The entry must live or die with the action it describes."""
        log_event(
            chain_db,
            actor_user_id=actor.id,
            action="vote_cast",
            entity_type="ballot",
            details="election=1",
        )
        chain_db.rollback()

        assert chain_db.query(AuditLog).count() == 0
        assert chain_db.query(AuditChainHead).count() == 0

    def test_a_position_cannot_be_reused(self, chain_db, actor):
        """The database rejects a duplicate sequence number outright."""
        first = append(chain_db, actor)

        duplicate = AuditLog(
            actor_user_id=actor.id,
            action="election_activated",
            entity_type="election",
            created_at=first.created_at,
            sequence_number=first.sequence_number,
            previous_hash=GENESIS_HASH,
            entry_hash="a" * 64,
        )
        chain_db.add(duplicate)

        with pytest.raises(IntegrityError):
            chain_db.commit()

        chain_db.rollback()


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class TestVerification:
    @pytest.fixture
    def chain_of_three(self, chain_db, actor):
        append(chain_db, actor, action="key_generated")
        append(chain_db, actor, action="election_activated", details="reason=manual")
        append(chain_db, actor, action="election_closed")
        return chain_db

    def test_an_empty_chain_verifies(self, chain_db):
        result = verify_audit_chain(chain_db)

        assert result.ok
        assert result.checked == 0

    def test_a_full_workflow_sequence_verifies(self, chain_db, actor):
        """The PR 7 workflow events must chain exactly like the original ones.

        Uses the real action names and detail shapes emitted by the admin and
        election routes, so a change to either that broke the chain would show
        up here rather than only in an end-to-end test.
        """
        workflow = [
            ("organizer_created", "user", "role=organizer"),
            ("election_created", "election", "status=draft"),
            ("election_updated", "election", "status=draft;fields=title,candidates"),
            ("election_title_changed", "election", "old_title=Old;new_title=New"),
            ("election_created", "election", "status=active"),
            ("key_generated", "election", None),
            ("eligibility_changed", "election", f"change=added;voter_id={actor.id}"),
            ("election_deadline_extended", "election", "old_end_date=A;new_end_date=B"),
            ("vote_cast", "ballot", "election=1"),
            ("election_closed", "election", "reason=manual"),
            ("results_published", "election", "reason=manual"),
            ("user_status_changed", "user", "old_status=active;new_status=inactive"),
            ("user_suspended", "user", "old_status=active;new_status=suspended"),
            ("user_unsuspended", "user", "old_status=suspended;new_status=active"),
            ("election_deleted", "election", "status=draft"),
            ("demo_reset_executed", "database", "scope=all_application_tables"),
        ]

        for action, entity_type, details in workflow:
            log_event(
                chain_db,
                actor_user_id=actor.id,
                action=action,
                entity_type=entity_type,
                details=details,
            )
        chain_db.commit()

        result = verify_audit_chain(chain_db)

        assert result.ok, [problem.message for problem in result.problems]
        assert result.checked == len(workflow)

        rows = entries(chain_db)
        assert [row.sequence_number for row in rows] == list(range(1, len(workflow) + 1))

    def test_an_untouched_chain_verifies(self, chain_of_three):
        result = verify_audit_chain(chain_of_three)

        assert result.ok, [problem.message for problem in result.problems]
        assert result.checked == 3
        assert result.problems == []

    def test_editing_an_entry_is_detected(self, chain_of_three):
        tamper(
            chain_of_three,
            "UPDATE audit_logs SET details = 'reason=rewritten' "
            "WHERE sequence_number = 2",
        )

        result = verify_audit_chain(chain_of_three)

        assert not result.ok
        assert "modified" in result.kinds
        assert any(problem.sequence_number == 2 for problem in result.problems)

    def test_changing_the_actor_is_detected(self, chain_of_three):
        tamper(
            chain_of_three,
            "UPDATE audit_logs SET action = 'vote_cast' WHERE sequence_number = 1",
        )

        result = verify_audit_chain(chain_of_three)

        assert "modified" in result.kinds

    def test_a_broken_previous_hash_is_detected(self, chain_of_three):
        tamper(
            chain_of_three,
            "UPDATE audit_logs SET previous_hash = :fake WHERE sequence_number = 3",
            fake="f" * 64,
        )

        result = verify_audit_chain(chain_of_three)

        assert not result.ok
        assert "broken_link" in result.kinds
        assert any(
            problem.kind == "broken_link" and problem.sequence_number == 3
            for problem in result.problems
        )

    def test_an_incorrect_entry_hash_is_detected(self, chain_of_three):
        tamper(
            chain_of_three,
            "UPDATE audit_logs SET entry_hash = :fake WHERE sequence_number = 2",
            fake="a" * 64,
        )

        result = verify_audit_chain(chain_of_three)

        assert not result.ok
        assert "modified" in result.kinds
        assert any(
            problem.kind == "modified" and problem.sequence_number == 2
            for problem in result.problems
        )

    def test_a_deleted_entry_is_detected(self, chain_of_three):
        tamper(chain_of_three, "DELETE FROM audit_logs WHERE sequence_number = 2")

        result = verify_audit_chain(chain_of_three)

        assert not result.ok
        assert "missing" in result.kinds

    def test_removing_the_newest_entry_is_detected(self, chain_of_three):
        """A gap check alone cannot see this — the head is what catches it."""
        tamper(chain_of_three, "DELETE FROM audit_logs WHERE sequence_number = 3")

        result = verify_audit_chain(chain_of_three)

        assert not result.ok
        assert "head_mismatch" in result.kinds

    def test_reordered_entries_are_detected(self, chain_of_three):
        """Swapping two entries' contents leaves both hashes wrong.

        sequence_number is part of the hashed content, so an entry cannot be
        moved to a different position and still verify.
        """
        tamper(
            chain_of_three,
            "UPDATE audit_logs SET action = CASE sequence_number "
            "WHEN 1 THEN 'election_activated' WHEN 2 THEN 'key_generated' END "
            "WHERE sequence_number IN (1, 2)",
        )

        result = verify_audit_chain(chain_of_three)

        assert not result.ok
        modified = {
            problem.sequence_number
            for problem in result.problems
            if problem.kind == "modified"
        }
        assert modified == {1, 2}

    def test_a_forged_replacement_entry_is_detected(self, chain_of_three):
        """Recomputing one entry's own hash is not enough to repair the chain.

        An attacker who edits an entry and fixes up its entry_hash still leaves
        the following entry pointing at the old hash.
        """
        rows = entries(chain_of_three)
        second = rows[1]

        forged_details = "reason=forged"
        forged_hash = compute_entry_hash(
            sequence_number=second.sequence_number,
            previous_hash=second.previous_hash,
            actor_user_id=second.actor_user_id,
            action=second.action,
            entity_type=second.entity_type,
            entity_id=second.entity_id,
            details=forged_details,
            created_at=second.created_at,
        )

        tamper(
            chain_of_three,
            "UPDATE audit_logs SET details = :details, entry_hash = :hash "
            "WHERE sequence_number = 2",
            details=forged_details,
            hash=forged_hash,
        )

        result = verify_audit_chain(chain_of_three)

        assert not result.ok
        assert "broken_link" in result.kinds
