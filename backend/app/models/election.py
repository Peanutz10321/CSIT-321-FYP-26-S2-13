import enum
import uuid

from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ElectionStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"
    archived = "archived"


class BallotType(str, enum.Enum):
    single = "single"
    multi = "multi"


class Election(Base):
    __tablename__ = "elections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(
        Enum(ElectionStatus, name="election_status"),
        nullable=False,
        default=ElectionStatus.draft,
    )

    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)

    # Ballot configuration. Defaults keep every existing caller a single-choice
    # ballot with exactly one selection.
    ballot_type = Column(
        Enum(BallotType, name="ballot_type"),
        nullable=False,
        default=BallotType.single,
        server_default=BallotType.single.value,
    )
    max_selections = Column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )

    # The Paillier private key deliberately does NOT live on this model —
    # see app/models/election_key.py and app/security/keystore.py.
    public_key_n = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    organizer = relationship("User", back_populates="organized_elections")

    @property
    def organizer_username(self):
        return self.organizer.username if self.organizer else None
    candidates = relationship("Candidate", back_populates="election", cascade="all, delete-orphan")
    election_voters = relationship("ElectionVoter", back_populates="election", cascade="all, delete-orphan")
    ballots = relationship("Ballot", back_populates="election", cascade="all, delete-orphan")
    candidate_results = relationship(
        "CandidateResult",
        back_populates="election",
        cascade="all, delete-orphan",
    )