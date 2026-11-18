from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models import (
    DamageSeverity,
    DamageSource,
    DamageType,
    InspectionKind,
    InspectionStatus,
    PhotoSide,
)


class InspectionCreate(BaseModel):
    vehicle_id: UUID
    kind: InspectionKind
    pair_id: UUID | None = None


class InspectionCreated(BaseModel):
    id: UUID
    status: InspectionStatus
    kind: InspectionKind
    pair_id: UUID
    required_sides: list[PhotoSide]


class InspectionStatusOut(BaseModel):
    id: UUID
    status: InspectionStatus


class DamageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: DamageType
    zone: str | None
    severity: DamageSeverity | None
    confidence: float
    polygon: list[list[float]]
    source: DamageSource
    is_new: bool | None
    llm_note: str | None


class PhotoQualityOut(BaseModel):
    ok: bool
    flags: list[str]
    score: float


class PhotoUploadedOut(BaseModel):
    photo_id: UUID
    side: PhotoSide
    width: int
    height: int
    quality: PhotoQualityOut


class PhotoOut(BaseModel):
    id: UUID
    side: PhotoSide
    url: str
    width: int | None
    height: int | None
    quality_score: float | None
    quality_flags: list[str] | None
    damages: list[DamageOut]


class InspectionOut(BaseModel):
    id: UUID
    vehicle_id: UUID
    driver_id: UUID
    kind: InspectionKind
    pair_id: UUID | None
    status: InspectionStatus
    failure_reason: str | None
    created_at: datetime
    finished_at: datetime | None
    photos: list[PhotoOut]
