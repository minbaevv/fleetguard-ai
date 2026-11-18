from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, CreatedAtMixin, UuidPkMixin

if TYPE_CHECKING:
    from app.db.models.inspection import Inspection
    from app.db.models.organization import Organization
    from app.db.models.report import Report


class Vehicle(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (UniqueConstraint("org_id", "plate", name="uq_vehicles_org_id_plate"),)

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plate: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    year: Mapped[int | None] = mapped_column(nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="vehicles")
    inspections: Mapped[list["Inspection"]] = relationship(back_populates="vehicle")
    reports: Mapped[list["Report"]] = relationship(back_populates="vehicle")
