from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ApiError
from app.db.models import (
    Inspection,
    InspectionKind,
    InspectionStatus,
    Photo,
    PhotoSide,
    User,
)
from app.schemas.inspections import InspectionCreate
from app.services.vehicles import get_vehicle

# Порядок важен для мастера съёмки: подсказки идут от передней части по кругу.
REQUIRED_SIDES: tuple[PhotoSide, ...] = (
    PhotoSide.front,
    PhotoSide.back,
    PhotoSide.left,
    PhotoSide.right,
)


def _resolve_pair_id(
    db: Session, org_id: UUID, vehicle_id: UUID, payload: InspectionCreate
) -> UUID:
    if payload.kind is InspectionKind.before:
        if payload.pair_id is not None:
            raise ApiError(
                422,
                "pair_id_not_allowed",
                "Для осмотра «до» pair_id назначает сервер",
            )
        return uuid4()

    if payload.pair_id is None:
        raise ApiError(
            422,
            "pair_id_required",
            "Для осмотра «после» укажите pair_id осмотра «до»",
        )

    before = db.scalar(
        select(Inspection).where(
            Inspection.org_id == org_id,
            Inspection.pair_id == payload.pair_id,
            Inspection.kind == InspectionKind.before,
        )
    )
    if before is None:
        raise ApiError(404, "inspection_pair_not_found", "Осмотр «до» с таким pair_id не найден")
    if before.vehicle_id != vehicle_id:
        raise ApiError(409, "pair_vehicle_mismatch", "Осмотр «до» относится к другой машине")
    if before.finished_at is None:
        raise ApiError(409, "before_not_finished", "Сначала завершите осмотр «до»")

    after_exists = db.scalar(
        select(Inspection.id).where(
            Inspection.org_id == org_id,
            Inspection.pair_id == payload.pair_id,
            Inspection.kind == InspectionKind.after,
        )
    )
    if after_exists:
        raise ApiError(409, "pair_complete", "Для этой пары уже есть осмотр «после»")

    return payload.pair_id


def create_inspection(db: Session, user: User, payload: InspectionCreate) -> Inspection:
    vehicle = get_vehicle(db, user.org_id, payload.vehicle_id)
    pair_id = _resolve_pair_id(db, user.org_id, vehicle.id, payload)

    inspection = Inspection(
        org_id=user.org_id,
        vehicle_id=vehicle.id,
        driver_id=user.id,
        kind=payload.kind,
        pair_id=pair_id,
        status=InspectionStatus.draft,
    )
    db.add(inspection)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "pair_complete", "Для этой пары уже есть осмотр «после»") from None
    db.refresh(inspection)
    return inspection


def get_inspection(db: Session, org_id: UUID, inspection_id: UUID) -> Inspection:
    inspection = db.scalar(
        select(Inspection).where(
            Inspection.id == inspection_id,
            Inspection.org_id == org_id,
        )
    )
    if inspection is None:
        # Чужой осмотр неотличим от несуществующего.
        raise ApiError(404, "inspection_not_found", "Осмотр не найден")
    return inspection


def get_inspection_detail(db: Session, org_id: UUID, inspection_id: UUID) -> Inspection:
    inspection = db.scalar(
        select(Inspection)
        .where(Inspection.id == inspection_id, Inspection.org_id == org_id)
        .options(selectinload(Inspection.photos).selectinload(Photo.damages))
    )
    if inspection is None:
        raise ApiError(404, "inspection_not_found", "Осмотр не найден")
    return inspection


def finish_inspection(db: Session, org_id: UUID, inspection_id: UUID) -> Inspection:
    inspection = get_inspection(db, org_id, inspection_id)
    if inspection.status is not InspectionStatus.draft:
        raise ApiError(409, "inspection_not_draft", "Осмотр уже завершён или обрабатывается")

    uploaded = set(db.scalars(select(Photo.side).where(Photo.inspection_id == inspection.id)))
    missing = [side for side in REQUIRED_SIDES if side not in uploaded]
    if missing:
        sides = ", ".join(side.value for side in missing)
        raise ApiError(409, "inspection_incomplete", f"Не хватает фото: {sides}")

    inspection.status = InspectionStatus.processing
    inspection.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(inspection)
    return inspection
