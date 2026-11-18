from uuid import UUID

from fastapi import APIRouter, UploadFile, status

from app.core.deps import CurrentUser, DbSession, StorageDep
from app.core.errors import ApiError
from app.db.models import PhotoSide
from app.schemas.inspections import (
    DamageOut,
    InspectionCreate,
    InspectionCreated,
    InspectionOut,
    InspectionStatusOut,
    PhotoOut,
    PhotoQualityOut,
    PhotoUploadedOut,
)
from app.services import inspections as inspection_service
from app.services import photos as photo_service
from app.services.storage import StorageError

router = APIRouter(prefix="/inspections", tags=["inspections"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=InspectionCreated)
def create_inspection(
    payload: InspectionCreate, user: CurrentUser, db: DbSession
) -> InspectionCreated:
    inspection = inspection_service.create_inspection(db, user, payload)
    return InspectionCreated(
        id=inspection.id,
        status=inspection.status,
        kind=inspection.kind,
        pair_id=inspection.pair_id,
        required_sides=list(inspection_service.REQUIRED_SIDES),
    )


@router.post(
    "/{inspection_id}/photos",
    status_code=status.HTTP_201_CREATED,
    response_model=PhotoUploadedOut,
)
def upload_photo(
    inspection_id: UUID,
    side: PhotoSide,
    file: UploadFile,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
) -> PhotoUploadedOut:
    uploaded = photo_service.upload_photo(db, user, storage, inspection_id, side, file.file)
    return PhotoUploadedOut(
        photo_id=uploaded.photo.id,
        side=uploaded.photo.side,
        width=uploaded.quality.width,
        height=uploaded.quality.height,
        quality=PhotoQualityOut(
            ok=uploaded.quality.ok,
            flags=list(uploaded.quality.flags),
            score=uploaded.quality.score,
        ),
    )


@router.post(
    "/{inspection_id}/finish",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=InspectionStatusOut,
)
def finish_inspection(inspection_id: UUID, user: CurrentUser, db: DbSession) -> InspectionStatusOut:
    inspection = inspection_service.finish_inspection(db, user.org_id, inspection_id)
    return InspectionStatusOut(id=inspection.id, status=inspection.status)


@router.get("/{inspection_id}", response_model=InspectionOut)
def get_inspection(
    inspection_id: UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> InspectionOut:
    inspection = inspection_service.get_inspection_detail(db, user.org_id, inspection_id)
    photos = sorted(
        inspection.photos,
        key=lambda photo: inspection_service.REQUIRED_SIDES.index(photo.side),
    )
    try:
        urls = {photo.id: storage.presigned_get_url(photo.storage_key) for photo in photos}
    except StorageError as exc:
        raise ApiError(502, exc.code, "Не удалось получить ссылку на фото") from exc

    return InspectionOut(
        id=inspection.id,
        vehicle_id=inspection.vehicle_id,
        driver_id=inspection.driver_id,
        kind=inspection.kind,
        pair_id=inspection.pair_id,
        status=inspection.status,
        failure_reason=inspection.failure_reason,
        created_at=inspection.created_at,
        finished_at=inspection.finished_at,
        photos=[
            PhotoOut(
                id=photo.id,
                side=photo.side,
                url=urls[photo.id],
                width=photo.width,
                height=photo.height,
                quality_score=photo.quality_score,
                quality_flags=photo.quality_flags,
                damages=[DamageOut.model_validate(damage) for damage in photo.damages],
            )
            for photo in photos
        ],
    )
