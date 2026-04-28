from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: UUID
    role: str
    status: str
    institution_id: str
    username: str
    full_name: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    username: str | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None