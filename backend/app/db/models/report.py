from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, CreatedAtMixin, UuidPkMixin
from app.db.models.types import json_type

if TYPE_CHECKING:
    from app.db.models.inspection import Inspection
    from app.db.models.vehicle import Vehicle


class Report(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "reports"

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    before_inspection_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="RESTRICT"), nullable=False
    )
    after_inspection_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[dict] = mapped_column(json_type(), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    est_cost_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    est_cost_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    vehicle: Mapped["Vehicle"] = relationship(back_populates="reports")
    before_inspection: Mapped["Inspection"] = relationship(foreign_keys=[before_inspection_id])
    after_inspection: Mapped["Inspection"] = relationship(foreign_keys=[after_inspection_id])
