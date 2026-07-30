from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.election import BallotType


class CandidateCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    photo_url: str | None = None
    display_order: int | None = None


class CandidateResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    photo_url: str | None = None
    display_order: int | None = None

    class Config:
        from_attributes = True


class ElectionDraftCreate(BaseModel):
    # Drafts may be partially filled, so everything except start_date (always sent
    # by the client) is optional. Full validation happens at create/activate time.
    title: str = ""
    description: str | None = None
    start_date: datetime
    end_date: datetime | None = None
    candidates: list[CandidateCreate] = []
    # Ballot configuration. Omitting these keeps the historical single-choice
    # behaviour; cross-field/candidate-count rules are enforced in the routes.
    ballot_type: BallotType = BallotType.single
    max_selections: int = 1
    # A draft carries its eligible voters too, so an organizer who saves and comes
    # back later resumes the whole configuration. Activation is what requires the
    # list to be non-empty.
    eligible_voter_external_ids: list[str] = Field(default_factory=list)


class ElectionCreate(ElectionDraftCreate):
    pass


class ElectionResponse(BaseModel):
    id: UUID
    organizer_id: UUID
    organizer_username: str | None = None
    title: str
    description: str | None = None
    status: str
    ballot_type: str
    max_selections: int
    start_date: datetime
    end_date: datetime | None = None
    candidates: list[CandidateResponse] = []

    class Config:
        from_attributes = True

class ExtendDeadlineRequest(BaseModel):
    new_end_date: datetime
    title: str | None = Field(default=None, min_length=1)


class ElectionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    candidates: list[CandidateCreate] | None = None
    ballot_type: BallotType | None = None
    max_selections: int | None = None
    # None means "leave the eligibility list alone"; a list replaces it wholesale.
    eligible_voter_external_ids: list[str] | None = None