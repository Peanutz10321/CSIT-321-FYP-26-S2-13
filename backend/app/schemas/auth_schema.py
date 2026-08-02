from typing import Annotated

from pydantic import BaseModel, EmailStr, Field

from app.models.user import GROUP_MAX_LENGTH
from app.security.password import PASSWORD_MIN_LENGTH


class RegisterRequest(BaseModel):
    username: str | None = None
    email: str | None = None
    # Public registration provisions voters and organizers, so the password rule
    # must be at least as strong as the old admin-only organizer path (min 8).
    # Kept optional so a genuinely absent password still yields the route's 400
    # "missing field" message rather than a schema 422; a supplied value is
    # length-checked. The role is deliberately a plain string, not a Literal, so
    # the route can answer 403 for system_admin instead of a blanket 422.
    password: Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH)] | None = None
    role: str = "voter"
    # Optional. Lets an organizer later add every member of an organisation at once.
    # Length-checked here so an oversized value is a 422 describing the field, rather
    # than a StringDataRightTruncation surfacing from PostgreSQL as a 500. Blank and
    # whitespace-only input is normalised to NULL when the account is built.
    group: Annotated[str, Field(max_length=GROUP_MAX_LENGTH)] | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
