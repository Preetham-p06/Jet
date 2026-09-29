"""Charter operators a workspace requests quotes from."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import OperatorSource


class Operator(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "operators"
    __table_args__ = (sa.UniqueConstraint("workspace_id", "normalized_name"),)

    name: Mapped[str] = mapped_column(sa.String(200))
    # Casefolded, punctuation-stripped name used for matching and uniqueness.
    normalized_name: Mapped[str] = mapped_column(sa.String(200))
    aliases: Mapped[list[str]] = mapped_column(JSONType, default=list)
    email: Mapped[str | None] = mapped_column(sa.String(320))
    email_domain: Mapped[str | None] = mapped_column(sa.String(255), index=True)
    phone: Mapped[str | None] = mapped_column(sa.String(32))  # E.164
    website: Mapped[str | None] = mapped_column(sa.String(500))
    home_base_icao: Mapped[str | None] = mapped_column(sa.String(4))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    source: Mapped[OperatorSource] = mapped_column(
        str_enum(OperatorSource), default=OperatorSource.MANUAL
    )
    is_archived: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
