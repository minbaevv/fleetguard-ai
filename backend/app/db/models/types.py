from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models.enums import (
    ChatRole,
    DamageSeverity,
    DamageSource,
    DamageType,
    InspectionKind,
    InspectionStatus,
    PhotoSide,
    UserRole,
)


def pg_enum(enum_cls: type, name: str) -> SAEnum:
    """Enum с нижним регистром значений: в БД лежит `admin`, а не `ADMIN`."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        native_enum=True,
    )


def json_type() -> JSON:
    """JSONB в PostgreSQL, обычный JSON в SQLite — тесты идут без внешней БД."""
    return JSON().with_variant(JSONB(), "postgresql")


USER_ROLE = pg_enum(UserRole, "user_role")
INSPECTION_KIND = pg_enum(InspectionKind, "inspection_kind")
INSPECTION_STATUS = pg_enum(InspectionStatus, "inspection_status")
PHOTO_SIDE = pg_enum(PhotoSide, "photo_side")
DAMAGE_TYPE = pg_enum(DamageType, "damage_type")
DAMAGE_SEVERITY = pg_enum(DamageSeverity, "damage_severity")
DAMAGE_SOURCE = pg_enum(DamageSource, "damage_source")
CHAT_ROLE = pg_enum(ChatRole, "chat_role")
