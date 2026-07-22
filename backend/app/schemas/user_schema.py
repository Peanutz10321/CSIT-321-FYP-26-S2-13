from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Annotated


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    status: str
    external_id: str
    username: str
    full_name: str | None = None
    email: EmailStr
    created_at: datetime
    updated_at: datetime



class UserUpdateRequest(BaseModel):
    username: Annotated[str, Field(min_length=1)] | None = None
    email: EmailStr | None = None
    password: str | None = None


class UserStatusUpdateRequest(BaseModel):
    status: str


class OrganizerCreateRequest(BaseModel):
    """Admin-supplied details for a provisioned organizer account.

    The role is not accepted from the client: this endpoint only ever creates
    organizers.
    """

    username: Annotated[str, Field(min_length=1)]
    email: EmailStr
    password: Annotated[str, Field(min_length=8)]
    full_name: str | None = None