import uuid

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    election_id = Column(UUID(as_uuid=True), ForeignKey("elections.id"), nullable=False)

    name = Column(String, nullable=False)
    description = Column(Text)
    photo_url = Column(String)
    display_order = Column(Integer)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    election = relationship("Election", back_populates="candidates")
    candidate_result = relationship(
        "CandidateResult",
        back_populates="candidate",
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint("election_id", "name", name="uq_candidates_election_name"),
    )