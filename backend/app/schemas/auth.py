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
    # POC placeholder for a real email service: in production this endpoint
    # would email the reset link and NOT return it in the API response. It's
    # returned here only because there is no email provider wired up yet.
    reset_token: str
    reset_url: str
