from fastapi import APIRouter, Response

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.security import AUTH_COOKIE_NAME, create_access_token
from app.db.models import Organization, User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    OrganizationOut,
    RegisterOrgRequest,
    UserOut,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookie(response: Response, user: User) -> None:
    token = create_access_token(user.id, user.org_id, user.role.value)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def _auth_response(organization: Organization, user: User) -> AuthResponse:
    return AuthResponse(
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(organization),
    )


@router.post("/register-org", status_code=201, response_model=AuthResponse)
def register_org(payload: RegisterOrgRequest, response: Response, db: DbSession) -> AuthResponse:
    organization, user = auth_service.register_organization(db, payload)
    _set_auth_cookie(response, user)
    return _auth_response(organization, user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> AuthResponse:
    user = auth_service.authenticate(db, payload)
    _set_auth_cookie(response, user)
    return _auth_response(user.organization, user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")


@router.get("/me", response_model=AuthResponse)
def me(user: CurrentUser) -> AuthResponse:
    return _auth_response(user.organization, user)
