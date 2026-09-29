"""Auth request and response bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.models.enums import Role
from app.permissions import Capability
from app.schemas.common import APIModel
from app.schemas.user import UserOut
from app.schemas.workspace import WorkspaceOut
from app.security.passwords import MIN_PASSWORD_LENGTH

LowerEmail = Annotated[EmailStr, AfterValidator(lambda e: e.lower())]
Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)]


class SignupIn(APIModel):
    workspace_name: str = Field(min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: LowerEmail
    password: Password


class LoginIn(APIModel):
    email: LowerEmail
    # No length rule on login, so old passwords never become unusable.
    password: str = Field(min_length=1, max_length=256)


class InviteAcceptIn(APIModel):
    token: str = Field(min_length=16, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    password: Password


class ChangePasswordIn(APIModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: Password


class MeOut(BaseModel):
    user: UserOut
    workspace: WorkspaceOut
    role: Role
    capabilities: list[Capability]


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_at: datetime
