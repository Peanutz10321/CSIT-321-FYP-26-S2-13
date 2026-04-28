from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    status: str
    institution_id: str
    username: str
    full_name: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime



class UserUpdateRequest(BaseModel):
    username: str | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None