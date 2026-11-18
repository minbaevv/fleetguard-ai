from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VehicleCreate(BaseModel):
    plate: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=120)
    year: int | None = Field(default=None, ge=1950, le=2100)

    @field_validator("plate", "model", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class VehicleUpdate(BaseModel):
    plate: str | None = Field(default=None, min_length=1, max_length=32)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    year: int | None = Field(default=None, ge=1950, le=2100)

    @field_validator("plate", "model", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> "VehicleUpdate":
        # PATCH { "plate": null } не должен ронять NOT NULL в БД.
        for field_name in ("plate", "model"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} не может быть null")
        return self


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    plate: str
    model: str
    year: int | None
    created_at: datetime
