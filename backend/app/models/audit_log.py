import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AuditLog(Base):
    """One security-relevant event, linked into a SHA-256 hash chain.

    ``previous_hash`` -> ``entry_hash`` ties every row to the one before it, so a
    row cannot be edited, removed, or reordered without breaking the links that
    follow. See app/security/audit.py for how the chain is built and verified.
    """

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(UUID(as_uuid=True))
    details = Column(Text)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # --- hash chain -------------------------------------------------------
    # Position in the global chain, starting at 1. Unique, so a duplicated or
    # re-used position is rejected by the database rather than silently
    # producing two "entry 7"s.
    sequence_number = Column(BigInteger, nullable=False)
    # entry_hash of the preceding entry (GENESIS_HASH for the first entry).
    previous_hash = Column(String(64), nullable=False)
    # SHA-256 over this entry's canonical JSON, which includes previous_hash.
    entry_hash = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("sequence_number", name="uq_audit_logs_sequence_number"),
    )

    actor = relationship("User", back_populates="audit_logs")


class AuditChainHead(Base):
    """Singleton row holding the tip of the audit chain.

    It exists to give writers one row to lock. Appending an event takes
    ``SELECT ... FOR UPDATE`` on this row, so concurrent transactions are
    serialised and can never claim the same sequence number or branch the chain.

    Keeping the tip here (rather than deriving it with ``MAX(sequence_number)``)
    also means truncating the end of audit_logs is detectable: the head still
    records the entry that should be there.
    """

    __tablename__ = "audit_chain_head"

    # Fixed singleton key (see CHAIN_ID in app/security/audit.py).
    id = Column(String(32), primary_key=True)

    sequence_number = Column(BigInteger, nullable=False)
    head_hash = Column(String(64), nullable=False)
    updated_at = Column(DateTime, nullable=False)
