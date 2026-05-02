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


class ElectionCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str | None = None
    start_date: datetime
    end_date: datetime
    candidates: list[CandidateCreate]


class ElectionResponse(BaseModel):
    id: UUID
    teacher_id: UUID
    title: str
    description: str | None = None
    status: str
    start_date: datetime
    end_date: datetime
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