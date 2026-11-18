from fastapi import APIRouter, status

from app.core.deps import AdminUser, DbSession
from app.schemas.auth import CreateUserRequest, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def create_user(payload: CreateUserRequest, admin: AdminUser, db: DbSession) -> UserOut:
    # org_id берём у администратора из сессии, а не из тела запроса.
    user = auth_service.create_user(db, admin.org_id, payload)
    return UserOut.model_validate(user)
