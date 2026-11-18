from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, CreatedAtMixin, UuidPkMixin
from app.db.models.enums import ChatRole
from app.db.models.types import CHAT_ROLE, json_type


class ChatMessage(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "chat_messages"

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[ChatRole] = mapped_column(CHAT_ROLE, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[dict | None] = mapped_column(json_type(), nullable=True)


class LlmUsage(UuidPkMixin, CreatedAtMixin, Base):
    """Контроль расходов на LLM: один вызов провайдера — одна запись."""

    __tablename__ = "llm_usage"

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
