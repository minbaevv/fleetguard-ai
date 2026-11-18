from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import hash_password, verify_password
from app.db.models import Organization, User, UserRole
from app.schemas.auth import CreateUserRequest, LoginRequest, RegisterOrgRequest


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _ensure_email_is_free(db: Session, email: str) -> None:
    if db.scalar(select(User.id).where(User.email == email)):
        raise ApiError(409, "email_taken", "Пользователь с таким email уже существует")


def register_organization(db: Session, payload: RegisterOrgRequest) -> tuple[Organization, User]:
    email = _normalize_email(payload.email)
    _ensure_email_is_free(db, email)

    organization = Organization(name=payload.organization_name.strip())
    user = User(
        organization=organization,
        email=email,
        password_hash=hash_password(payload.password),
        name=payload.name.strip(),
        role=UserRole.admin,
    )
    db.add_all([organization, user])
    db.commit()
    return organization, user


def authenticate(db: Session, payload: LoginRequest) -> User:
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        # Одинаковый текст для неизвестного email и неверного пароля: не раскрываем базу.
        raise ApiError(401, "invalid_credentials", "Неверный email или пароль")
    return user


def create_user(db: Session, org_id: UUID, payload: CreateUserRequest) -> User:
    email = _normalize_email(payload.email)
    _ensure_email_is_free(db, email)

    user = User(
        org_id=org_id,
        email=email,
        password_hash=hash_password(payload.password),
        name=payload.name.strip(),
        role=UserRole(payload.role),
    )
    db.add(user)
    db.commit()
    return user
