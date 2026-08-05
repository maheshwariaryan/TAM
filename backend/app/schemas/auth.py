"""Auth request/response schemas.

UserPublic deliberately has no hashed_password field — there is nothing to
strip in the API layer because the field simply doesn't exist on this model.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class UserPublic(BaseModel):
    id: str
    email: str
    full_name: str
    created_at: datetime


class ForgotPasswordResponse(BaseModel):
    message: str
