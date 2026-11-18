from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession, ManagerUser
from app.schemas.vehicles import VehicleCreate, VehicleOut, VehicleUpdate
from app.services import vehicles as vehicle_service

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    user: CurrentUser,
    db: DbSession,
    search: str | None = Query(default=None, max_length=120),
) -> list[VehicleOut]:
    vehicles = vehicle_service.list_vehicles(db, user.org_id, search)
    return [VehicleOut.model_validate(vehicle) for vehicle in vehicles]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=VehicleOut)
def create_vehicle(payload: VehicleCreate, user: ManagerUser, db: DbSession) -> VehicleOut:
    vehicle = vehicle_service.create_vehicle(db, user.org_id, payload)
    return VehicleOut.model_validate(vehicle)


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: UUID, user: CurrentUser, db: DbSession) -> VehicleOut:
    vehicle = vehicle_service.get_vehicle(db, user.org_id, vehicle_id)
    return VehicleOut.model_validate(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: UUID, payload: VehicleUpdate, user: ManagerUser, db: DbSession
) -> VehicleOut:
    vehicle = vehicle_service.update_vehicle(db, user.org_id, vehicle_id, payload)
    return VehicleOut.model_validate(vehicle)


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: UUID, user: ManagerUser, db: DbSession) -> None:
    vehicle_service.delete_vehicle(db, user.org_id, vehicle_id)
