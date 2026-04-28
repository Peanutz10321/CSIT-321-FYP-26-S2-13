import enum
import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class EligibilityStatus(str, enum.Enum):
    eligible = "eligible"
    revoked = "revoked"


class ElectionVoter(Base):
    __tablename__ = "election_voters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    election_id = Column(UUID(as_uuid=True), ForeignKey("elections.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    eligibility_status = Column(
        Enum(EligibilityStatus, name="eligibility_status"),
        nullable=False,
        default=EligibilityStatus.eligible,
    )

    voted_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    election = relationship("Election", back_populates="election_voters")
    student = relationship("User", back_populates="election_voter_records")
    ballot = relationship("Ballot", back_populates="election_voter", uselist=False)

    __table_args__ = (
        UniqueConstraint("election_id", "student_id", name="uq_election_voters_election_student"),
    )