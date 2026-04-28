from pydantic import BaseModel, EmailStr
from typing import Optional


class RegisterRequest(BaseModel):
    institution_id: str
    username: str
    full_name: str
    email: EmailStr
    password: str
    role: str  # "student" or "teacher"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"