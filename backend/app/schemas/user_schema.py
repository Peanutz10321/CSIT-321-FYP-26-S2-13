from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Annotated

from app.models.user import GROUP_MAX_LENGTH
from app.security.password import PASSWORD_MIN_LENGTH


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    status: str
    external_id: str
    username: str
    full_name: str | None = None
    email: EmailStr
    # The organisation the account belongs to, or None. Returned everywhere a user
    # is read — /users/me, the admin views and the group listing — so an account
    # holder can see the group an organizer would enrol them through.
    group: str | None = None
    created_at: datetime
    updated_at: datetime



class UserUpdateRequest(BaseModel):
    username: Annotated[str, Field(min_length=1)] | None = None
    email: EmailStr | None = None
    # Same minimum as registration. Without it an account could be created with a
    # compliant password and then immediately lowered to a weaker one, which made
    # the registration rule advisory rather than enforced. Omitted (or blank) still
    # means "keep the current password"; a supplied value is length-checked.
    password: Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH)] | None = None
    # Bounded to the column width, as at registration. Unlike the fields above,
    # None is a real value here: it clears the group. The route distinguishes
    # "sent as null/blank" from "not sent at all" via model_fields_set.
    group: Annotated[str, Field(max_length=GROUP_MAX_LENGTH)] | None = None


class UserStatusUpdateRequest(BaseModel):
    status: str