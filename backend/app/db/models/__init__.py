"""Все модели импортируются здесь, чтобы Alembic видел полный metadata."""

from app.db.models.base import Base
from app.db.models.chat import ChatMessage, LlmUsage
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
from app.db.models.inspection import Damage, Inspection, Photo
from app.db.models.organization import Organization
from app.db.models.report import Report
from app.db.models.user import User
from app.db.models.vehicle import Vehicle

__all__ = [
    "Base",
    "ChatMessage",
    "ChatRole",
    "Damage",
    "DamageSeverity",
    "DamageSource",
    "DamageType",
    "Inspection",
    "InspectionKind",
    "InspectionStatus",
    "LlmUsage",
    "Organization",
    "Photo",
    "PhotoSide",
    "Report",
    "User",
    "UserRole",
    "Vehicle",
]
