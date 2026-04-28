import enum
import uuid

from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey
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


class Election(Base):
    __tablename__ = "elections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(
        Enum(ElectionStatus, name="election_status"),
        nullable=False,
        default=ElectionStatus.draft,
    )

    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    teacher = relationship("User", back_populates="elections")
    candidates = relationship("Candidate", back_populates="election", cascade="all, delete-orphan")
    election_voters = relationship("ElectionVoter", back_populates="election", cascade="all, delete-orphan")
    ballots = relationship("Ballot", back_populates="election", cascade="all, delete-orphan")
    candidate_results = relationship(
        "CandidateResult",
        back_populates="election",
        cascade="all, delete-orphan",
    )