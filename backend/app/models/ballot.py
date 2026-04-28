import enum
import uuid

from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class BulletinStatus(str, enum.Enum):
    published = "published"
    hidden_invalid = "hidden_invalid"


class Ballot(Base):
    __tablename__ = "ballots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    election_id = Column(UUID(as_uuid=True), ForeignKey("elections.id"), nullable=False)
    election_voter_id = Column(UUID(as_uuid=True), ForeignKey("election_voters.id"), nullable=False, unique=True)

    encrypted_vote = Column(Text, nullable=False)
    vote_hash = Column(String, nullable=False, unique=True)
    receipt_code = Column(String, nullable=False, unique=True)

    submitted_at = Column(DateTime, nullable=False, server_default=func.now())
    bulletin_status = Column(
        Enum(BulletinStatus, name="bulletin_status"),
        nullable=False,
        default=BulletinStatus.published,
    )

    election = relationship("Election", back_populates="ballots")
    election_voter = relationship("ElectionVoter", back_populates="ballot")