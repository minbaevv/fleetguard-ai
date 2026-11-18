from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, CreatedAtMixin, UuidPkMixin
from app.db.models.enums import (
    DamageSeverity,
    DamageSource,
    DamageType,
    InspectionKind,
    InspectionStatus,
    PhotoSide,
)
from app.db.models.types import (
    DAMAGE_SEVERITY,
    DAMAGE_SOURCE,
    DAMAGE_TYPE,
    INSPECTION_KIND,
    INSPECTION_STATUS,
    PHOTO_SIDE,
    json_type,
)

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.vehicle import Vehicle


class Inspection(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "inspections"
    __table_args__ = (
        # Один pair_id описывает ровно один осмотр «до» и один «после».
        UniqueConstraint("pair_id", "kind", name="uq_inspections_pair_id_kind"),
        Index("ix_inspections_org_vehicle_created", "org_id", "vehicle_id", "created_at"),
    )

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    driver_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[InspectionKind] = mapped_column(INSPECTION_KIND, nullable=False)
    pair_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    status: Mapped[InspectionStatus] = mapped_column(
        INSPECTION_STATUS, nullable=False, default=InspectionStatus.draft
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vehicle: Mapped["Vehicle"] = relationship(back_populates="inspections")
    driver: Mapped["User"] = relationship()
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )
    damages: Mapped[list["Damage"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )


class Photo(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "photos"
    __table_args__ = (
        UniqueConstraint("inspection_id", "side", name="uq_photos_inspection_id_side"),
    )

    inspection_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    side: Mapped[PhotoSide] = mapped_column(PHOTO_SIDE, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags: Mapped[list[str] | None] = mapped_column(json_type(), nullable=True)

    inspection: Mapped["Inspection"] = relationship(back_populates="photos")
    damages: Mapped[list["Damage"]] = relationship(back_populates="photo")


class Damage(UuidPkMixin, Base):
    __tablename__ = "damages"
    __table_args__ = (Index("ix_damages_org_id_is_new", "org_id", "is_new"),)

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    inspection_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    photo_id: Mapped[UUID] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[DamageType] = mapped_column(DAMAGE_TYPE, nullable=False)
    zone: Mapped[str | None] = mapped_column(String(120), nullable=True)
    severity: Mapped[DamageSeverity | None] = mapped_column(DAMAGE_SEVERITY, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # Нормализованные координаты 0..1, чтобы не зависеть от размера фото.
    polygon: Mapped[list[list[float]]] = mapped_column(json_type(), nullable=False)
    source: Mapped[DamageSource] = mapped_column(DAMAGE_SOURCE, nullable=False)
    is_new: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    llm_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    inspection: Mapped["Inspection"] = relationship(back_populates="damages")
    photo: Mapped["Photo"] = relationship(back_populates="damages")
