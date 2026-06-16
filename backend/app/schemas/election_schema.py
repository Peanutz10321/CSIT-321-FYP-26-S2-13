from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


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


class ElectionCreate(ElectionDraftCreate):
    voter_institution_ids: list[str] = []


class ElectionResponse(BaseModel):
    id: UUID
    teacher_id: UUID
    teacher_username: str | None = None
    title: str
    description: str | None = None
    status: str
    start_date: datetime
    end_date: datetime | None = None
    candidates: list[CandidateResponse] = []

    class Config:
        from_attributes = True

class ExtendDeadlineRequest(BaseModel):
    new_end_date: datetime


class ElectionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    candidates: list[CandidateCreate] | None = None