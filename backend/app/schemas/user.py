"""Users and invites."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import AwareDatetime, BaseModel, EmailStr

from app.models.enums import Role
from app.schemas.common import APIModel, ORMModel

InviteState = Literal["pending", "accepted", "revoked", "expired"]


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    last_login_at: AwareDatetime | None
    created_at: AwareDatetime


class UserPatch(APIModel):
    role: Role | None = None
    is_active: bool | None = None


class InviteCreate(APIModel):
    email: EmailStr
    role: Role


class InviteOut(ORMModel):
    id: uuid.UUID
    email: str
    role: Role
    state: InviteState
    invited_by_id: uuid.UUID | None
    expires_at: AwareDatetime
    accepted_at: AwareDatetime | None
    revoked_at: AwareDatetime | None
    created_at: AwareDatetime


class InviteCreatedOut(BaseModel):
    """The raw token appears only here, inside `invite_url`, exactly once."""

    id: uuid.UUID
    email: str
    role: Role
    invite_url: str
    expires_at: AwareDatetime
