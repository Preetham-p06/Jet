"""Initial schema.

Reviewed by hand after autogenerate: the two circular foreign keys
(trips.booked_quote_id, proposals.accepted_option_id) are added after both
tables exist, and boolean server defaults use sa.true()/sa.false() so the
migration is portable to Postgres.

Revision ID: 0001
Revises:
Create Date: 2026-09-29 20:42:57.777608
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("review_threshold", sa.Integer(), server_default="75", nullable=False),
        sa.Column(
            "default_markup_pct",
            sa.Numeric(precision=5, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("base_currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column(
            "scoring_weights",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "default_markup_pct >= 0 AND default_markup_pct <= 100",
            name=op.f("ck_workspaces_markup_range"),
        ),
        sa.CheckConstraint(
            "review_threshold >= 50 AND review_threshold <= 100",
            name=op.f("ck_workspaces_review_threshold_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("slug", name=op.f("uq_workspaces_slug")),
    )
    op.create_table(
        "operators",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column(
            "aliases",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_domain", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("home_base_icao", sa.String(length=4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("manual", "extraction", name="operatorsource", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_operators_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operators")),
        sa.UniqueConstraint(
            "workspace_id",
            "normalized_name",
            name=op.f("uq_operators_workspace_id_normalized_name"),
        ),
    )
    with op.batch_alter_table("operators", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_operators_email_domain"), ["email_domain"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_operators_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "broker", "assistant", name="role", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_users_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_workspace_id"), ["workspace_id"], unique=False)

    op.create_table(
        "invites",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "broker", "assistant", name="role", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["accepted_user_id"],
            ["users.id"],
            name=op.f("fk_invites_accepted_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.id"],
            name=op.f("fk_invites_invited_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_invites_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invites")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invites_token_hash")),
    )
    with op.batch_alter_table("invites", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_invites_workspace_id"), ["workspace_id"], unique=False)

    op.create_table(
        "trips",
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "sourcing",
                "quoted",
                "proposed",
                "booked",
                "cancelled",
                "lost",
                name="tripstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "trip_type",
            sa.Enum(
                "one_way", "round_trip", "multi_leg", name="triptype", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("pax", sa.Integer(), nullable=False),
        sa.Column("client_name", sa.String(length=200), nullable=True),
        sa.Column("client_email", sa.String(length=320), nullable=True),
        sa.Column(
            "preferences",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("booked_quote_id", sa.Uuid(), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("pax >= 1", name=op.f("ck_trips_pax_positive")),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_trips_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_trips_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trips")),
        sa.UniqueConstraint(
            "workspace_id", "reference", name=op.f("uq_trips_workspace_id_reference")
        ),
    )
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trips_workspace_id"), ["workspace_id"], unique=False)
        batch_op.create_index(
            "ix_trips_workspace_id_created_at", ["workspace_id", "created_at"], unique=False
        )
        batch_op.create_index(
            "ix_trips_workspace_id_status", ["workspace_id", "status"], unique=False
        )

    op.create_table(
        "audit_events",
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "actor_kind",
            sa.Enum("user", "system", "public", name="actorkind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("actor_label", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("trip_id", sa.Uuid(), nullable=True),
        sa.Column(
            "before",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "after",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name=op.f("fk_audit_events_trip_id_trips"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_audit_events_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index("ix_audit_events_entity", ["entity_type", "entity_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_events_trip_id"), ["trip_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_events_workspace_id"), ["workspace_id"], unique=False
        )
        batch_op.create_index(
            "ix_audit_events_workspace_id_created_at", ["workspace_id", "created_at"], unique=False
        )

    op.create_table(
        "proposals",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "sent",
                "accepted",
                "booked",
                "declined",
                "cancelled",
                "superseded",
                name="proposalstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("client_name", sa.String(length=200), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("markup_pct", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("share_token", sa.String(length=64), nullable=True),
        sa.Column("share_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_by_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_option_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_by_name", sa.String(length=200), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "markup_pct >= 0 AND markup_pct <= 100", name=op.f("ck_proposals_markup_range")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_proposals_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sent_by_id"],
            ["users.id"],
            name=op.f("fk_proposals_sent_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["proposals.id"],
            name=op.f("fk_proposals_supersedes_id_proposals"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name=op.f("fk_proposals_trip_id_trips"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_proposals_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposals")),
        sa.UniqueConstraint("share_token", name=op.f("uq_proposals_share_token")),
    )
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_proposals_trip_id"), ["trip_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_proposals_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "trip_legs",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("origin_icao", sa.String(length=4), nullable=False),
        sa.Column("destination_icao", sa.String(length=4), nullable=False),
        sa.Column("depart_local", sa.DateTime(), nullable=False),
        sa.Column("depart_tz", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name=op.f("fk_trip_legs_trip_id_trips"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_trip_legs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trip_legs")),
        sa.UniqueConstraint("trip_id", "seq", name=op.f("uq_trip_legs_trip_id_seq")),
    )
    with op.batch_alter_table("trip_legs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trip_legs_trip_id"), ["trip_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_trip_legs_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "trip_operators",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "requested",
                "quoted",
                "declined",
                name="tripoperatorstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum(
                "email",
                "phone",
                "sms",
                "whatsapp",
                "portal",
                "other",
                name="requestchannel",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_reason", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_trip_operators_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["operators.id"],
            name=op.f("fk_trip_operators_operator_id_operators"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name=op.f("fk_trip_operators_trip_id_trips"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_trip_operators_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trip_operators")),
        sa.UniqueConstraint(
            "trip_id", "operator_id", name=op.f("uq_trip_operators_trip_id_operator_id")
        ),
    )
    with op.batch_alter_table("trip_operators", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_trip_operators_operator_id"), ["operator_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_trip_operators_trip_id"), ["trip_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_trip_operators_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "quotes",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("trip_operator_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "withdrawn",
                "rejected",
                "superseded",
                name="quotestatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("original_currency", sa.String(length=3), nullable=False),
        sa.Column(
            "pricing_basis",
            sa.Enum("flat", "hourly", name="pricingbasis", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("headline_cents", sa.Integer(), nullable=True),
        sa.Column("known_total_cents", sa.Integer(), nullable=True),
        sa.Column("upper_total_cents", sa.Integer(), nullable=True),
        sa.Column("is_fully_priced", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("open_blocking_flags", sa.Integer(), server_default="0", nullable=False),
        sa.Column("open_info_flags", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pending_review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("quote_confidence", sa.Integer(), nullable=True),
        sa.Column("confidence_mean", sa.Double(), nullable=True),
        sa.Column("fit_score", sa.Integer(), nullable=True),
        sa.Column(
            "fit_breakdown",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("is_recommended", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("eligible_for_proposal", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "eligibility_reasons",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("aircraft_model", sa.String(length=120), nullable=True),
        sa.Column(
            "aircraft_category",
            sa.Enum(
                "turboprop",
                "very_light",
                "light",
                "midsize",
                "super_midsize",
                "heavy",
                "ultra_long_range",
                "airliner",
                name="aircraftcategory",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("tail_number", sa.String(length=16), nullable=True),
        sa.Column("seats", sa.Integer(), nullable=True),
        sa.Column("wifi", sa.Boolean(), nullable=True),
        sa.Column("flight_time_minutes", sa.Integer(), nullable=True),
        sa.Column("departure_local", sa.DateTime(), nullable=True),
        sa.Column(
            "availability",
            sa.Enum(
                "confirmed",
                "available",
                "subject_to",
                "tentative",
                "on_request",
                "unavailable",
                name="availability",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("first_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calc_version", sa.String(length=32), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["operators.id"],
            name=op.f("fk_quotes_operator_id_operators"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name=op.f("fk_quotes_trip_id_trips"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["trip_operator_id"],
            ["trip_operators.id"],
            name=op.f("fk_quotes_trip_operator_id_trip_operators"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_quotes_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quotes")),
    )
    with op.batch_alter_table("quotes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_quotes_operator_id"), ["operator_id"], unique=False)
        batch_op.create_index(
            "ix_quotes_trip_id_operator_id", ["trip_id", "operator_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_quotes_workspace_id"), ["workspace_id"], unique=False)

    op.create_table(
        "fee_observations",
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=True),
        sa.Column("airport_icao", sa.String(length=4), nullable=False),
        sa.Column(
            "airport_role",
            sa.Enum("departure", "arrival", name="airportrole", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column(
            "aircraft_category",
            sa.Enum(
                "turboprop",
                "very_light",
                "light",
                "midsize",
                "super_midsize",
                "heavy",
                "ultra_long_range",
                "airliner",
                name="aircraftcategory",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "fee_category",
            sa.Enum(
                "positioning",
                "ramp_handling",
                "fuel_surcharge",
                "catering",
                "crew_overnight",
                "crew",
                "overnight",
                "landing",
                "deicing",
                "international",
                "fet",
                "segment_fees",
                "taxes",
                "wifi_fee",
                "other",
                name="feecategory",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column(
            "amount_status",
            sa.Enum(
                "stated",
                "included",
                "estimated",
                "not_stated",
                "waived",
                "not_applicable",
                name="amountstatus",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "extracted", "verified", name="observationsource", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["operators.id"],
            name=op.f("fk_fee_observations_operator_id_operators"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            name=op.f("fk_fee_observations_quote_id_quotes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_fee_observations_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fee_observations")),
        sa.UniqueConstraint(
            "quote_id",
            "airport_icao",
            "airport_role",
            "fee_category",
            name=op.f("uq_fee_observations_quote_id_airport_icao_airport_role_fee_category"),
        ),
    )
    with op.batch_alter_table("fee_observations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_fee_observations_lookup",
            ["workspace_id", "airport_icao", "fee_category", "month"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_fee_observations_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "proposal_options",
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_recommended", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("cost_basis_cents", sa.Integer(), nullable=False),
        sa.Column("markup_pct_override", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("markup_cents", sa.Integer(), nullable=False),
        sa.Column("client_total_cents", sa.Integer(), nullable=False),
        sa.Column(
            "client_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "broker_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name=op.f("fk_proposal_options_proposal_id_proposals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            name=op.f("fk_proposal_options_quote_id_quotes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_proposal_options_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposal_options")),
        sa.UniqueConstraint(
            "proposal_id", "quote_id", name=op.f("uq_proposal_options_proposal_id_quote_id")
        ),
    )
    with op.batch_alter_table("proposal_options", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_proposal_options_proposal_id"), ["proposal_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_proposal_options_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "recommendations",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("recommended_quote_id", sa.Uuid(), nullable=True),
        sa.Column("algorithm_version", sa.String(length=16), nullable=False),
        sa.Column(
            "weights",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "ranking",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recommended_quote_id"],
            ["quotes.id"],
            name=op.f("fk_recommendations_recommended_quote_id_quotes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name=op.f("fk_recommendations_trip_id_trips"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_recommendations_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendations")),
    )
    with op.batch_alter_table("recommendations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_recommendations_trip_id_computed_at", ["trip_id", "computed_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_recommendations_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "source_documents",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("operator_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "pdf",
                "email",
                "sms",
                "whatsapp",
                "text",
                "image",
                name="documentkind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum(
                "pdf_upload",
                "email",
                "sms",
                "whatsapp",
                "paste",
                "other",
                name="documentchannel",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("media_type", sa.String(length=127), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("is_scanned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "text_pages",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("sender", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "intent",
            sa.Enum(
                "quote",
                "revision",
                "decline",
                "other",
                name="documentintent",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "extraction_status",
            sa.Enum(
                "pending",
                "processing",
                "succeeded",
                "failed",
                "needs_manual",
                name="extractionstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("extractor", sa.String(length=32), nullable=True),
        sa.Column("extractor_version", sa.String(length=64), nullable=True),
        sa.Column("extractor_model", sa.String(length=64), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column(
            "extraction_result",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "extraction_usage",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["operators.id"],
            name=op.f("fk_source_documents_operator_id_operators"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["source_documents.id"],
            name=op.f("fk_source_documents_parent_id_source_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            name=op.f("fk_source_documents_quote_id_quotes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name=op.f("fk_source_documents_trip_id_trips"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_source_documents_uploaded_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_source_documents_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_documents")),
        sa.UniqueConstraint("trip_id", "sha256", name=op.f("uq_source_documents_trip_id_sha256")),
    )
    with op.batch_alter_table("source_documents", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_source_documents_quote_id"), ["quote_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_source_documents_trip_id"), ["trip_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_source_documents_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "processing_events",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "step",
            sa.Enum(
                "ingest",
                "extract",
                "normalize",
                "validate",
                "compare",
                "recommendation",
                name="processingstep",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "level",
            sa.Enum("info", "warn", "ok", "error", name="eventlevel", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column(
            "data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            name=op.f("fk_processing_events_quote_id_quotes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name=op.f("fk_processing_events_source_document_id_source_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name=op.f("fk_processing_events_trip_id_trips"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_processing_events_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_events")),
    )
    with op.batch_alter_table("processing_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_processing_events_trip_id_created_at", ["trip_id", "created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_processing_events_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "quote_fields",
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column(
            "group",
            sa.Enum("scalar", "fee", name="fieldgroup", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column(
            "value_type",
            sa.Enum(
                "text",
                "int",
                "number",
                "bool",
                "money",
                "datetime",
                "duration",
                "fee",
                name="valuetype",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "original_value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "current_value",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column(
            "extractor",
            sa.Enum(
                "rules", "claude", "manual", name="extractorkind", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("extractor_version", sa.String(length=64), nullable=True),
        sa.Column("snippet", sa.String(length=500), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("snippet_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "extracted",
                "verified",
                "accepted",
                "edited",
                name="fieldstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("locked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=1000), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "corroborating_source_ids",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(locked AND status <> 'extracted') OR (NOT locked AND status = 'extracted')",
            name=op.f("ck_quote_fields_locked_iff_reviewed"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100", name=op.f("ck_quote_fields_confidence_range")
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            name=op.f("fk_quote_fields_quote_id_quotes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_quote_fields_reviewed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name=op.f("fk_quote_fields_source_document_id_source_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["quote_fields.id"],
            name=op.f("fk_quote_fields_superseded_by_id_quote_fields"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_quote_fields_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_fields")),
    )
    with op.batch_alter_table("quote_fields", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_quote_fields_quote_id"), ["quote_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_quote_fields_workspace_id"), ["workspace_id"], unique=False
        )
        batch_op.create_index(
            "uq_quote_fields_current_key",
            ["quote_id", "key"],
            unique=True,
            sqlite_where=sa.text("is_current"),
            postgresql_where=sa.text("is_current"),
        )

    op.create_table(
        "fee_lines",
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("field_id", sa.Uuid(), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "positioning",
                "ramp_handling",
                "fuel_surcharge",
                "catering",
                "crew_overnight",
                "crew",
                "overnight",
                "landing",
                "deicing",
                "international",
                "fet",
                "segment_fees",
                "taxes",
                "wifi_fee",
                "other",
                name="feecategory",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column(
            "amount_status",
            sa.Enum(
                "stated",
                "included",
                "estimated",
                "not_stated",
                "waived",
                "not_applicable",
                name="amountstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "included_by",
            sa.Enum("explicit", "all_in", name="includedby", native_enum=False, length=32),
            nullable=True,
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("original_amount_minor", sa.Integer(), nullable=True),
        sa.Column("original_currency", sa.String(length=3), nullable=True),
        sa.Column(
            "unit",
            sa.Enum(
                "flat",
                "per_hour",
                "per_night",
                "per_leg",
                "per_pax",
                "percent",
                name="feeunit",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("percent", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("explicitly_extra", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("counts_in_known", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("counts_in_upper", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("estimate_cents", sa.Integer(), nullable=True),
        sa.Column("estimate_basis", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column(
            "review_status",
            sa.Enum(
                "extracted",
                "verified",
                "accepted",
                "edited",
                name="fieldstatus",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["field_id"],
            ["quote_fields.id"],
            name=op.f("fk_fee_lines_field_id_quote_fields"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"],
            ["quotes.id"],
            name=op.f("fk_fee_lines_quote_id_quotes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name=op.f("fk_fee_lines_source_document_id_source_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_fee_lines_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fee_lines")),
    )
    with op.batch_alter_table("fee_lines", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_fee_lines_quote_id"), ["quote_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_fee_lines_workspace_id"), ["workspace_id"], unique=False
        )

    op.create_table(
        "flags",
        sa.Column("trip_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("field_id", sa.Uuid(), nullable=True),
        sa.Column(
            "fee_category",
            sa.Enum(
                "positioning",
                "ramp_handling",
                "fuel_surcharge",
                "catering",
                "crew_overnight",
                "crew",
                "overnight",
                "landing",
                "deicing",
                "international",
                "fet",
                "segment_fees",
                "taxes",
                "wifi_fee",
                "other",
                name="feecategory",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column(
            "type",
            sa.Enum(
                "ambiguous_charge",
                "expected_fee_missing",
                "conditional_charge",
                "learned_fee_missing",
                "total_mismatch",
                "conflicting_values",
                "conflict_with_locked",
                "missing_required_field",
                "capacity_insufficient",
                "hourly_estimate",
                "unknown_currency",
                "extraction_failed",
                "ocr_unavailable",
                "quote_expired",
                "all_in_itemized_conflict",
                "fx_converted",
                "snippet_unverified",
                "fee_outlier",
                "schedule_mismatch",
                "value_revised",
                name="flagtype",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "info", "warning", "critical", name="flagseverity", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("blocking", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fingerprint", sa.String(length=200), nullable=False),
        sa.Column("data_hash", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column(
            "details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "open", "resolved", "dismissed", name="flagstatus", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "resolution",
            sa.Enum(
                "confirmed_amount",
                "accepted_estimate",
                "confirmed_included",
                "not_applicable",
                "dismissed",
                "acknowledged",
                "use_new_value",
                "keep_current",
                "auto_cleared",
                name="flagresolution",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("resolution_note", sa.String(length=1000), nullable=True),
        sa.Column("resolved_by_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["field_id"],
            ["quote_fields.id"],
            name=op.f("fk_flags_field_id_quote_fields"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["quote_id"], ["quotes.id"], name=op.f("fk_flags_quote_id_quotes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["users.id"],
            name=op.f("fk_flags_resolved_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name=op.f("fk_flags_source_document_id_source_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name=op.f("fk_flags_trip_id_trips"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_flags_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flags")),
        sa.UniqueConstraint("quote_id", "fingerprint", name=op.f("uq_flags_quote_id_fingerprint")),
    )
    with op.batch_alter_table("flags", schema=None) as batch_op:
        batch_op.create_index("ix_flags_trip_id_status", ["trip_id", "status"], unique=False)
        batch_op.create_index(batch_op.f("ix_flags_workspace_id"), ["workspace_id"], unique=False)

    # Circular references, added once both sides exist.
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_trips_booked_quote_id_quotes"),
            "quotes",
            ["booked_quote_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_proposals_accepted_option_id_proposal_options"),
            "proposal_options",
            ["accepted_option_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_proposals_accepted_option_id_proposal_options"), type_="foreignkey"
        )
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_trips_booked_quote_id_quotes"), type_="foreignkey")

    with op.batch_alter_table("flags", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_flags_workspace_id"))
        batch_op.drop_index("ix_flags_trip_id_status")

    op.drop_table("flags")
    with op.batch_alter_table("fee_lines", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_fee_lines_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_fee_lines_quote_id"))

    op.drop_table("fee_lines")
    with op.batch_alter_table("quote_fields", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_quote_fields_current_key",
            sqlite_where=sa.text("is_current"),
            postgresql_where=sa.text("is_current"),
        )
        batch_op.drop_index(batch_op.f("ix_quote_fields_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_quote_fields_quote_id"))

    op.drop_table("quote_fields")
    with op.batch_alter_table("processing_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_processing_events_workspace_id"))
        batch_op.drop_index("ix_processing_events_trip_id_created_at")

    op.drop_table("processing_events")
    with op.batch_alter_table("source_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_source_documents_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_source_documents_trip_id"))
        batch_op.drop_index(batch_op.f("ix_source_documents_quote_id"))

    op.drop_table("source_documents")
    with op.batch_alter_table("recommendations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recommendations_workspace_id"))
        batch_op.drop_index("ix_recommendations_trip_id_computed_at")

    op.drop_table("recommendations")
    with op.batch_alter_table("proposal_options", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposal_options_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_proposal_options_proposal_id"))

    op.drop_table("proposal_options")
    with op.batch_alter_table("fee_observations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_fee_observations_workspace_id"))
        batch_op.drop_index("ix_fee_observations_lookup")

    op.drop_table("fee_observations")
    with op.batch_alter_table("quotes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_quotes_workspace_id"))
        batch_op.drop_index("ix_quotes_trip_id_operator_id")
        batch_op.drop_index(batch_op.f("ix_quotes_operator_id"))

    op.drop_table("quotes")
    with op.batch_alter_table("trip_operators", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trip_operators_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_trip_operators_trip_id"))
        batch_op.drop_index(batch_op.f("ix_trip_operators_operator_id"))

    op.drop_table("trip_operators")
    with op.batch_alter_table("trip_legs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trip_legs_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_trip_legs_trip_id"))

    op.drop_table("trip_legs")
    with op.batch_alter_table("proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_proposals_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_proposals_trip_id"))

    op.drop_table("proposals")
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_events_workspace_id_created_at")
        batch_op.drop_index(batch_op.f("ix_audit_events_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_audit_events_trip_id"))
        batch_op.drop_index("ix_audit_events_entity")

    op.drop_table("audit_events")
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.drop_index("ix_trips_workspace_id_status")
        batch_op.drop_index("ix_trips_workspace_id_created_at")
        batch_op.drop_index(batch_op.f("ix_trips_workspace_id"))

    op.drop_table("trips")
    with op.batch_alter_table("invites", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_invites_workspace_id"))

    op.drop_table("invites")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_workspace_id"))

    op.drop_table("users")
    with op.batch_alter_table("operators", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_operators_workspace_id"))
        batch_op.drop_index(batch_op.f("ix_operators_email_domain"))

    op.drop_table("operators")
    op.drop_table("workspaces")
