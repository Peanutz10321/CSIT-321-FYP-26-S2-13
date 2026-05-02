from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CandidateResultResponse(BaseModel):
    candidate_id: UUID
    candidate_name: str
    total_votes: int
    published_at: datetime | None = None


class ElectionResultResponse(BaseModel):
    election_id: UUID
    election_title: str
    status: str
    results: list[CandidateResultResponse]