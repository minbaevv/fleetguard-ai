"""initial schema

Revision ID: fe91e5882983
Revises:
Create Date: 2026-11-18 16:11:26.108904
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fe91e5882983"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())

# PostgreSQL не удаляет enum-типы вместе с таблицами, поэтому чистим их явно,
# иначе повторный upgrade после downgrade упадёт на «type already exists».
ENUM_TYPES = (
    "user_role",
    "chat_role",
    "inspection_kind",
    "inspection_status",
    "photo_side",
    "damage_type",
    "damage_severity",
    "damage_source",
)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )
    op.create_table(
        "llm_usage",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_llm_usage_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_usage")),
    )
    op.create_index(op.f("ix_llm_usage_org_id"), "llm_usage", ["org_id"], unique=False)

    op.create_table(
        "users",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.Enum("admin", "manager", "driver", name="user_role"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_users_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_org_id"), "users", ["org_id"], unique=False)

    op.create_table(
        "vehicles",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("plate", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_vehicles_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vehicles")),
        sa.UniqueConstraint("org_id", "plate", name="uq_vehicles_org_id_plate"),
    )
    op.create_index(op.f("ix_vehicles_org_id"), "vehicles", ["org_id"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Enum("user", "assistant", name="chat_role"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", JSONB, nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_chat_messages_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_messages_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    op.create_index(op.f("ix_chat_messages_org_id"), "chat_messages", ["org_id"], unique=False)
    op.create_index(op.f("ix_chat_messages_user_id"), "chat_messages", ["user_id"], unique=False)

    op.create_table(
        "inspections",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Enum("before", "after", name="inspection_kind"), nullable=False),
        sa.Column("pair_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "uploading",
                "processing",
                "done",
                "failed",
                name="inspection_status",
            ),
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"],
            ["users.id"],
            name=op.f("fk_inspections_driver_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_inspections_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_inspections_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspections")),
        sa.UniqueConstraint("pair_id", "kind", name="uq_inspections_pair_id_kind"),
    )
    op.create_index(op.f("ix_inspections_driver_id"), "inspections", ["driver_id"], unique=False)
    op.create_index(op.f("ix_inspections_org_id"), "inspections", ["org_id"], unique=False)
    op.create_index(
        "ix_inspections_org_vehicle_created",
        "inspections",
        ["org_id", "vehicle_id", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_inspections_pair_id"), "inspections", ["pair_id"], unique=False)
    op.create_index(op.f("ix_inspections_vehicle_id"), "inspections", ["vehicle_id"], unique=False)

    op.create_table(
        "photos",
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "side", sa.Enum("front", "back", "left", "right", name="photo_side"), nullable=False
        ),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("quality_flags", JSONB, nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_photos_inspection_id_inspections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photos")),
        sa.UniqueConstraint("inspection_id", "side", name="uq_photos_inspection_id_side"),
        sa.UniqueConstraint("storage_key", name=op.f("uq_photos_storage_key")),
    )
    op.create_index(op.f("ix_photos_inspection_id"), "photos", ["inspection_id"], unique=False)

    op.create_table(
        "reports",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("before_inspection_id", sa.Uuid(), nullable=False),
        sa.Column("after_inspection_id", sa.Uuid(), nullable=False),
        sa.Column("body", JSONB, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("pdf_key", sa.String(length=512), nullable=True),
        sa.Column("est_cost_min", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("est_cost_max", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["after_inspection_id"],
            ["inspections.id"],
            name=op.f("fk_reports_after_inspection_id_inspections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["before_inspection_id"],
            ["inspections.id"],
            name=op.f("fk_reports_before_inspection_id_inspections"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_reports_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name=op.f("fk_reports_vehicle_id_vehicles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index(op.f("ix_reports_org_id"), "reports", ["org_id"], unique=False)
    op.create_index(op.f("ix_reports_vehicle_id"), "reports", ["vehicle_id"], unique=False)

    op.create_table(
        "damages",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("photo_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "dent",
                "scratch",
                "crack",
                "glass_shatter",
                "lamp_broken",
                "tire_flat",
                name="damage_type",
            ),
            nullable=False,
        ),
        sa.Column("zone", sa.String(length=120), nullable=True),
        sa.Column(
            "severity",
            sa.Enum("low", "medium", "high", name="damage_severity"),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("polygon", JSONB, nullable=False),
        sa.Column("source", sa.Enum("cv", "llm", name="damage_source"), nullable=False),
        sa.Column("is_new", sa.Boolean(), nullable=True),
        sa.Column("llm_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["inspections.id"],
            name=op.f("fk_damages_inspection_id_inspections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_damages_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["photo_id"],
            ["photos.id"],
            name=op.f("fk_damages_photo_id_photos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_damages")),
    )
    op.create_index(op.f("ix_damages_inspection_id"), "damages", ["inspection_id"], unique=False)
    op.create_index("ix_damages_org_id_is_new", "damages", ["org_id", "is_new"], unique=False)
    op.create_index(op.f("ix_damages_photo_id"), "damages", ["photo_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_damages_photo_id"), table_name="damages")
    op.drop_index("ix_damages_org_id_is_new", table_name="damages")
    op.drop_index(op.f("ix_damages_inspection_id"), table_name="damages")
    op.drop_table("damages")

    op.drop_index(op.f("ix_reports_vehicle_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_org_id"), table_name="reports")
    op.drop_table("reports")

    op.drop_index(op.f("ix_photos_inspection_id"), table_name="photos")
    op.drop_table("photos")

    op.drop_index(op.f("ix_inspections_vehicle_id"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_pair_id"), table_name="inspections")
    op.drop_index("ix_inspections_org_vehicle_created", table_name="inspections")
    op.drop_index(op.f("ix_inspections_org_id"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_driver_id"), table_name="inspections")
    op.drop_table("inspections")

    op.drop_index(op.f("ix_chat_messages_user_id"), table_name="chat_messages")
    op.drop_index(op.f("ix_chat_messages_org_id"), table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index(op.f("ix_vehicles_org_id"), table_name="vehicles")
    op.drop_table("vehicles")

    op.drop_index(op.f("ix_users_org_id"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_llm_usage_org_id"), table_name="llm_usage")
    op.drop_table("llm_usage")

    op.drop_table("organizations")

    # Enum-типы создавались неявно вместе с таблицами, удаляем вручную.
    op.execute(sa.text("DROP TYPE IF EXISTS damage_source"))
    op.execute(sa.text("DROP TYPE IF EXISTS damage_severity"))
    op.execute(sa.text("DROP TYPE IF EXISTS damage_type"))
    op.execute(sa.text("DROP TYPE IF EXISTS photo_side"))
    op.execute(sa.text("DROP TYPE IF EXISTS inspection_status"))
    op.execute(sa.text("DROP TYPE IF EXISTS inspection_kind"))
    op.execute(sa.text("DROP TYPE IF EXISTS chat_role"))
    op.execute(sa.text("DROP TYPE IF EXISTS user_role"))
