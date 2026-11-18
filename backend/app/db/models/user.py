from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, CreatedAtMixin, UuidPkMixin
from app.db.models.enums import UserRole
from app.db.models.types import USER_ROLE

if TYPE_CHECKING:
    from app.db.models.organization import Organization


class User(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "users"

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(USER_ROLE, nullable=False, default=UserRole.driver)

    organization: Mapped["Organization"] = relationship(back_populates="users")

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.admin
