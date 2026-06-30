from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AddElectionVoterRequest(BaseModel):
    external_id: str = Field(..., min_length=1)


class ElectionVoterResponse(BaseModel):
    id: UUID
    election_id: UUID
    voter_id: UUID
    eligibility_status: str
    voted_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ElectionVoterDetailResponse(BaseModel):
    id: UUID
    election_id: UUID
    voter_id: UUID
    voter_external_id: str
    voter_username: str
    voter_email: str
    eligibility_status: str
    voted_at: datetime | None = None
    created_at: datetime