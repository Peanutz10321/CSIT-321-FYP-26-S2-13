"""
Append-only audit trail for security-relevant events.

Rows are added to the caller's session and commit atomically with the action
they describe — an audited action and its audit row succeed or fail together.
Never update or delete audit rows.

Actions used so far:
  vote_cast, key_generated, election_activated   (security-fixes branch)
  election_closed, results_published, eligibility_changed   (ballot branch)
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_event(
    db: Session,
    actor_user_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID | None = None,
    details: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
    return entry
