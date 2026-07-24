"""
Append-only, hash-chained audit trail for security-relevant events.

Rows are added to the caller's session and commit atomically with the action
they describe — an audited action and its audit row succeed or fail together.
This module never commits. Never update or delete audit rows.

The chain
---------
Every entry stores its position (``sequence_number``), the hash of the entry
before it (``previous_hash``), and a SHA-256 over its own canonical JSON
(``entry_hash``). Because ``previous_hash`` is part of the hashed content, each
entry commits to the entire history preceding it: editing, deleting, or
reordering a row breaks every link after it, which ``verify_audit_chain``
reports.

Appending locks the singleton ``audit_chain_head`` row, so two concurrent
transactions cannot claim the same sequence number or fork the chain. The lock
is held until the caller's transaction ends.

What this does and does not prove
---------------------------------
The chain detects database-only tampering: a reader with direct table access who
edits, deletes, or reorders audit rows cannot keep the hashes consistent without
rewriting every following entry and the head. It is not proof against a
compromised backend, which can rewrite the whole chain legitimately. A trusted
external checkpoint of the head hash would be needed for that.

Never record a voter's selection. ``details`` carries identifiers and status
transitions only — no plaintext choices, candidate selections, private keys, or
decrypted ballot data.

Actions used so far:
  vote_cast, key_generated, election_activated,
  election_closed, results_published, eligibility_changed
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.time import now_sgt
from app.models.audit_log import AuditChainHead, AuditLog

# Canonicalisation and hashing live in a frozen v1 module (see the warning
# there). They are re-exported here so the application code and tests have one
# stable import surface while the actual byte format can never drift. Migration
# 0004 imports the frozen module directly, not this one.
from app.security.audit_hash_v1 import (  # noqa: F401  (re-exported)
    AUDIT_HASH_VERSION,
    GENESIS_HASH,
    _timestamp_text,
    _uuid_text,
    canonical_entry,
    compute_entry_hash,
)


# The chain is global: one ordered sequence covering every audited event.
CHAIN_ID = "global"


# ---------------------------------------------------------------------------
# Structured details
# ---------------------------------------------------------------------------

# The only field NAMES an audit ``details`` value may carry. This is a guard on
# structure, not on content: it stops a whole category being added by mistake (a
# field literally named ``email`` or ``candidate_name`` raises), but it cannot vet
# the *values* — those are the caller's responsibility. Keep it minimal, and add
# a name here only for data that is safe to record. Never add a field for a
# candidate selection, receipt code, password, secret, private key or ciphertext.
_ALLOWED_DETAIL_FIELDS = frozenset(
    {
        "status",
        "old_status",
        "new_status",
        "old_title",
        "new_title",
        "fields",
        "change",
        "voter_id",
        "old_end_date",
        "new_end_date",
        "role",
        "scope",
        "reason",
    }
)


def audit_details(**fields) -> str:
    """Build a deterministic JSON ``details`` string from allowlisted fields.

    Prefer this over hand-built ``key=value;key=value`` strings: a user-controlled
    value such as an election title can contain ``;``, ``=``, quotes or newlines,
    which makes a delimited string ambiguous to parse and easy to spoof. JSON with
    sorted keys and compact separators is unambiguous and stable.

    Only names in ``_ALLOWED_DETAIL_FIELDS`` are accepted; anything else raises.
    That is a guard on the *field name*, not the value: it stops an unapproved
    category (say a field named ``email``) being added by accident, but it does
    not and cannot guarantee the values are free of personal data. The caller is
    responsible for passing only safe values — never a candidate selection,
    receipt code, secret or ballot material. ``None`` values are dropped so an
    absent field and an explicit null read the same.
    """
    unknown = set(fields) - _ALLOWED_DETAIL_FIELDS
    if unknown:
        raise ValueError(
            f"audit_details received disallowed field(s): {', '.join(sorted(unknown))}"
        )

    payload = {key: value for key, value in fields.items() if value is not None}

    # ensure_ascii=False keeps non-ASCII text readable; sorted keys and compact
    # separators keep the output deterministic regardless of call order.
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry_hash_for_row(row: AuditLog) -> str:
    """Recompute a stored row's hash from its own current contents."""
    return compute_entry_hash(
        sequence_number=row.sequence_number,
        previous_hash=row.previous_hash,
        actor_user_id=row.actor_user_id,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        details=row.details,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# Appending
# ---------------------------------------------------------------------------


def _chain_head(db: Session) -> AuditChainHead:
    """Return the chain head, locked for the rest of the caller's transaction.

    ``with_for_update()`` is deliberately used *without* ``populate_existing()``:
    when several events are logged in one transaction, the second call must keep
    the in-memory sequence number the first call advanced, not overwrite it with
    the not-yet-flushed database value.

    SQLite drops the locking clause, but it serialises writers at the database
    level, so the ordering guarantee still holds there.
    """
    head = (
        db.query(AuditChainHead)
        .filter(AuditChainHead.id == CHAIN_ID)
        .with_for_update()
        .first()
    )
    if head is not None:
        return head

    # The row may already have been created earlier in this same uncommitted
    # transaction, in which case it is pending rather than queryable.
    for pending in db.new:
        if isinstance(pending, AuditChainHead) and pending.id == CHAIN_ID:
            return pending

    # First event on a database whose head row was never seeded (migration 0003
    # seeds it; a create_all() database has no seed step).
    head = AuditChainHead(
        id=CHAIN_ID,
        sequence_number=0,
        head_hash=GENESIS_HASH,
        updated_at=now_sgt(),
    )
    db.add(head)
    return head


def log_event(
    db: Session,
    actor_user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    details: str | None = None,
) -> AuditLog:
    """Append one event to the chain, in the caller's transaction.

    Does not commit: the entry becomes durable only when the caller commits the
    action it describes.
    """
    head = _chain_head(db)

    sequence_number = head.sequence_number + 1
    previous_hash = head.head_hash
    # Set in Python rather than by the column's server default, so the value
    # that gets hashed is exactly the value that gets stored.
    created_at = now_sgt()

    entry_hash = compute_entry_hash(
        sequence_number=sequence_number,
        previous_hash=previous_hash,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        created_at=created_at,
    )

    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        created_at=created_at,
        sequence_number=sequence_number,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
    )
    db.add(entry)

    head.sequence_number = sequence_number
    head.head_hash = entry_hash
    head.updated_at = created_at

    return entry


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditChainProblem:
    # One of: missing, broken_link, modified, head_mismatch
    kind: str
    sequence_number: int | None
    message: str


@dataclass(frozen=True)
class AuditChainVerification:
    checked: int
    problems: list[AuditChainProblem]

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def kinds(self) -> set[str]:
        return {problem.kind for problem in self.problems}

    def __bool__(self) -> bool:
        return self.ok


def verify_audit_chain(db: Session) -> AuditChainVerification:
    """Walk the chain from the first entry to the head and report every break.

    Detects:

    * modified   - an entry's contents no longer hash to its stored entry_hash;
    * missing    - a gap in the sequence, i.e. a deleted entry;
    * reordered  - sequence_number is part of the hashed content, so swapping
                   two entries' contents fails their hash checks;
    * broken     - previous_hash does not match the preceding entry's hash;
    * truncated  - the head still points past the last surviving entry.
    """
    rows = db.query(AuditLog).order_by(AuditLog.sequence_number).all()

    problems: list[AuditChainProblem] = []
    expected_sequence = 1
    expected_previous = GENESIS_HASH

    for row in rows:
        if row.sequence_number != expected_sequence:
            problems.append(
                AuditChainProblem(
                    kind="missing",
                    sequence_number=row.sequence_number,
                    message=(
                        f"sequence gap: expected entry {expected_sequence}, "
                        f"found {row.sequence_number}"
                    ),
                )
            )

        if row.previous_hash != expected_previous:
            problems.append(
                AuditChainProblem(
                    kind="broken_link",
                    sequence_number=row.sequence_number,
                    message=(
                        f"entry {row.sequence_number} does not link to the "
                        f"preceding entry"
                    ),
                )
            )

        if _entry_hash_for_row(row) != row.entry_hash:
            problems.append(
                AuditChainProblem(
                    kind="modified",
                    sequence_number=row.sequence_number,
                    message=(
                        f"entry {row.sequence_number} does not match its own "
                        f"entry_hash"
                    ),
                )
            )

        # Resynchronise so one break is reported once rather than for every
        # entry that follows it.
        expected_sequence = row.sequence_number + 1
        expected_previous = row.entry_hash

    problems.extend(_verify_head(db, rows))

    return AuditChainVerification(checked=len(rows), problems=problems)


def _verify_head(db: Session, rows: list[AuditLog]) -> list[AuditChainProblem]:
    """Compare the recorded tip against the last surviving entry."""
    head = (
        db.query(AuditChainHead)
        .filter(AuditChainHead.id == CHAIN_ID)
        .first()
    )

    if head is None:
        if rows:
            return [
                AuditChainProblem(
                    kind="head_mismatch",
                    sequence_number=None,
                    message="audit entries exist but the chain head is missing",
                )
            ]
        return []

    if not rows:
        if head.sequence_number != 0:
            return [
                AuditChainProblem(
                    kind="head_mismatch",
                    sequence_number=head.sequence_number,
                    message=(
                        f"chain head records entry {head.sequence_number} but "
                        f"the audit log is empty"
                    ),
                )
            ]
        return []

    last = rows[-1]
    if head.sequence_number != last.sequence_number or head.head_hash != last.entry_hash:
        return [
            AuditChainProblem(
                kind="head_mismatch",
                sequence_number=head.sequence_number,
                message=(
                    f"chain head records entry {head.sequence_number} but the "
                    f"last stored entry is {last.sequence_number}"
                ),
            )
        ]

    return []
