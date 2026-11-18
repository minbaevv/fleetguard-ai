from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Inspection, Report, Vehicle
from app.schemas.vehicles import VehicleCreate, VehicleUpdate


def normalize_plate(plate: str) -> str:
    # Пробелы и регистр не должны создавать дубли «А123ВС» / «а123вс».
    return " ".join(plate.split()).upper()


def list_vehicles(db: Session, org_id: UUID, search: str | None = None) -> list[Vehicle]:
    query = select(Vehicle).where(Vehicle.org_id == org_id)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Vehicle.plate.ilike(pattern), Vehicle.model.ilike(pattern)))
    return list(db.scalars(query.order_by(Vehicle.plate)))


def get_vehicle(db: Session, org_id: UUID, vehicle_id: UUID) -> Vehicle:
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.org_id == org_id))
    if vehicle is None:
        # Чужая машина и несуществующая неотличимы снаружи: не раскрываем чужие id.
        raise ApiError(404, "vehicle_not_found", "Машина не найдена")
    return vehicle


def _ensure_plate_is_free(
    db: Session, org_id: UUID, plate: str, exclude_id: UUID | None = None
) -> None:
    query = select(Vehicle.id).where(Vehicle.org_id == org_id, Vehicle.plate == plate)
    if exclude_id is not None:
        query = query.where(Vehicle.id != exclude_id)
    if db.scalar(query):
        raise ApiError(409, "plate_taken", "Машина с таким номером уже есть в организации")


def create_vehicle(db: Session, org_id: UUID, payload: VehicleCreate) -> Vehicle:
    plate = normalize_plate(payload.plate)
    _ensure_plate_is_free(db, org_id, plate)

    vehicle = Vehicle(
        org_id=org_id,
        plate=plate,
        model=payload.model.strip(),
        year=payload.year,
    )
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "plate_taken", "Машина с таким номером уже есть") from None
    db.refresh(vehicle)
    return vehicle


def update_vehicle(db: Session, org_id: UUID, vehicle_id: UUID, payload: VehicleUpdate) -> Vehicle:
    vehicle = get_vehicle(db, org_id, vehicle_id)
    changes = payload.model_dump(exclude_unset=True)

    if "plate" in changes and changes["plate"] is not None:
        plate = normalize_plate(changes["plate"])
        _ensure_plate_is_free(db, org_id, plate, exclude_id=vehicle.id)
        changes["plate"] = plate
    if "model" in changes and changes["model"] is not None:
        changes["model"] = changes["model"].strip()

    for field, value in changes.items():
        setattr(vehicle, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "plate_taken", "Машина с таким номером уже есть") from None
    db.refresh(vehicle)
    return vehicle


def delete_vehicle(db: Session, org_id: UUID, vehicle_id: UUID) -> None:
    vehicle = get_vehicle(db, org_id, vehicle_id)

    has_inspections = db.scalar(
        select(func.count(Inspection.id)).where(Inspection.vehicle_id == vehicle.id)
    )
    has_reports = db.scalar(select(func.count(Report.id)).where(Report.vehicle_id == vehicle.id))
    if has_inspections or has_reports:
        raise ApiError(
            409,
            "vehicle_has_history",
            "У машины есть осмотры или акты — удаление запрещено",
        )

    db.delete(vehicle)
    db.commit()
