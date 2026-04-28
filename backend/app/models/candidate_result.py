import uuid

from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class CandidateResult(Base):
    __tablename__ = "candidate_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    election_id = Column(UUID(as_uuid=True), ForeignKey("elections.id"), nullable=False)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=False)

    total_votes = Column(Integer, nullable=False, default=0)
    published_at = Column(DateTime)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    election = relationship("Election", back_populates="candidate_results")
    candidate = relationship("Candidate", back_populates="candidate_result")
    candidate_result = relationship(
        "CandidateResult",
        back_populates="candidate",
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint("election_id", "candidate_id", name="uq_candidate_results_election_candidate"),
    )