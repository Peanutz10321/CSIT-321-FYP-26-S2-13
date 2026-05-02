from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class VoteCreate(BaseModel):
    election_id: UUID
    candidate_id: UUID


class VoteResponse(BaseModel):
    id: UUID
    election_id: UUID
    election_voter_id: UUID
    encrypted_vote: str
    vote_hash: str
    receipt_code: str
    submitted_at: datetime
    bulletin_status: str

    class Config:
        from_attributes = True


class VoteHistoryResponse(BaseModel):
    id: UUID
    election_id: UUID
    election_title: str
    receipt_code: str
    submitted_at: datetime
    bulletin_status: str