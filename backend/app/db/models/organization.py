from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, CreatedAtMixin, UuidPkMixin

if TYPE_CHECKING:
    from app.db.models.user import User
    from app.db.models.vehicle import Vehicle


class Organization(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="organization")
