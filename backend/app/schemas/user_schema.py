from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Annotated


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    status: str
    institution_id: str
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