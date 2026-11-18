from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import UserRole

Name = Annotated[str, Field(min_length=2, max_length=200)]
Password = Annotated[str, Field(min_length=8, max_length=128)]


class RegisterOrgRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    name: Name
    email: EmailStr
    password: Password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class CreateUserRequest(BaseModel):
    name: Name
    email: EmailStr
    password: Password
    role: Literal["manager", "driver"]


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    email: str
    name: str
    role: UserRole


class AuthResponse(BaseModel):
    user: UserOut
    organization: OrganizationOut
