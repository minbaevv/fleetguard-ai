from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import AUTH_COOKIE_NAME, decode_access_token
from app.db.models import User, UserRole
from app.db.session import get_session


def get_db() -> Iterator[Session]:
    yield from get_session()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise ApiError(401, "unauthorized", "Требуется вход в систему")

    payload = decode_access_token(token)
    if not payload:
        raise ApiError(401, "unauthorized", "Сессия истекла или недействительна")

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        raise ApiError(401, "unauthorized", "Недействительный токен") from None

    user = db.get(User, user_id)
    if user is None:
        raise ApiError(401, "unauthorized", "Пользователь не найден")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.admin:
        raise ApiError(403, "forbidden", "Недостаточно прав")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
