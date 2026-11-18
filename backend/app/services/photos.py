"""Приём фото осмотра: проверка файла, нормализация и сохранение в хранилище."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import IO, Final
from uuid import UUID, uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import InspectionStatus, Photo, PhotoSide, User
from app.services import inspections as inspection_service
from app.services.quality import QualityResult, QualityThresholds, analyze_quality
from app.services.storage import StorageError, StorageService

logger = logging.getLogger(__name__)

# Content-Type из запроса подделывается тривиально, поэтому формат проверяем по содержимому.
ALLOWED_IMAGE_FORMATS: Final = frozenset({"JPEG", "PNG", "WEBP"})
STORED_CONTENT_TYPE: Final = "image/jpeg"

_READ_CHUNK_BYTES: Final = 64 * 1024


@dataclass(frozen=True, slots=True)
class UploadedPhoto:
    photo: Photo
    quality: QualityResult


def thresholds_from_settings() -> QualityThresholds:
    return QualityThresholds(
        min_width=settings.quality_min_width,
        min_height=settings.quality_min_height,
        blur_threshold=settings.quality_blur_threshold,
        min_brightness=settings.quality_min_brightness,
        max_brightness=settings.quality_max_brightness,
    )


def _read_upload(file: IO[bytes]) -> bytes:
    # Читаем кусками: файл на 2 ГБ не должен целиком попасть в память до проверки лимита.
    chunks: list[bytes] = []
    total = 0
    while chunk := file.read(_READ_CHUNK_BYTES):
        total += len(chunk)
        if total > settings.max_upload_bytes:
            limit = settings.max_upload_bytes
            limit_text = f"{limit // (1024 * 1024)} МБ" if limit >= 1024 * 1024 else f"{limit} Б"
            raise ApiError(413, "file_too_large", f"Файл больше {limit_text}")
        chunks.append(chunk)
    if not chunks:
        raise ApiError(400, "empty_file", "Файл пуст")
    return b"".join(chunks)


def _decode_image(data: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(data)) as probe:
            if probe.format not in ALLOWED_IMAGE_FORMATS:
                raise ApiError(
                    415,
                    "unsupported_image_type",
                    "Поддерживаются JPEG, PNG и WebP",
                )
            # Проверяем пиксели до полного декодирования: защита от «бомб декомпрессии».
            if probe.width * probe.height > settings.max_image_pixels:
                raise ApiError(413, "image_too_large", "Слишком большое разрешение изображения")
            probe.load()
            return probe.copy()
    except ApiError:
        raise
    except Image.DecompressionBombError:
        raise ApiError(413, "image_too_large", "Слишком большое разрешение изображения") from None
    except (UnidentifiedImageError, OSError, ValueError):
        # Битый или обрезанный файл: Pillow кидает OSError, неизвестный формат — своё исключение.
        raise ApiError(415, "invalid_image", "Не удалось прочитать изображение") from None


def _normalize(image: Image.Image) -> Image.Image:
    # EXIF-ориентация с телефона: без неё вертикальное фото приходит «лежа».
    oriented = ImageOps.exif_transpose(image)
    if oriented.mode in {"RGBA", "LA", "P"}:
        # Прозрачный PNG при переводе в JPEG стал бы чёрным: подкладываем белый фон.
        rgba = oriented.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return oriented.convert("RGB")


def _encode_jpeg(image: Image.Image) -> bytes:
    buffer = BytesIO()
    # Перекодирование заодно убирает EXIF и прочие метаданные из файла.
    image.save(buffer, format="JPEG", quality=settings.photo_jpeg_quality, optimize=True)
    return buffer.getvalue()


def _storage_key(org_id: UUID, inspection_id: UUID) -> str:
    # Случайный ключ: по ссылке нельзя перебрать чужие фото и угадать имя файла.
    return f"photos/{org_id}/{inspection_id}/{uuid4().hex}.jpg"


def _delete_object(storage: StorageService, key: str) -> None:
    try:
        storage.delete(key)
    except StorageError:
        # Старый файл-сирота не должен ломать уже сохранённое фото.
        logger.warning("Не удалось удалить объект хранилища %s", key)


def upload_photo(
    db: Session,
    user: User,
    storage: StorageService,
    inspection_id: UUID,
    side: PhotoSide,
    file: IO[bytes],
) -> UploadedPhoto:
    inspection = inspection_service.get_inspection(db, user.org_id, inspection_id)
    if inspection.status is not InspectionStatus.draft:
        raise ApiError(409, "inspection_not_draft", "Осмотр уже завершён")

    data = _read_upload(file)
    image = _normalize(_decode_image(data))
    quality = analyze_quality(image, thresholds_from_settings())
    payload = _encode_jpeg(image)
    key = _storage_key(inspection.org_id, inspection.id)

    try:
        storage.upload(key, payload, STORED_CONTENT_TYPE)
    except StorageError as exc:
        raise ApiError(502, exc.code, "Не удалось сохранить фото") from exc

    photo = db.scalar(select(Photo).where(Photo.inspection_id == inspection.id, Photo.side == side))
    previous_key = photo.storage_key if photo is not None else None
    if photo is None:
        photo = Photo(inspection_id=inspection.id, side=side, storage_key=key)
        db.add(photo)
    else:
        photo.storage_key = key

    photo.width = quality.width
    photo.height = quality.height
    photo.quality_score = quality.score
    photo.quality_flags = list(quality.flags)

    try:
        db.commit()
    except IntegrityError:
        # Параллельная загрузка той же стороны: строку успел создать другой запрос.
        db.rollback()
        _delete_object(storage, key)
        raise ApiError(
            409, "photo_conflict", "Фото этой стороны уже загружается, повторите"
        ) from None
    except Exception:
        # Новый объект уже в хранилище: без отката он останется сиротой.
        db.rollback()
        _delete_object(storage, key)
        raise
    db.refresh(photo)

    if previous_key is not None and previous_key != key:
        _delete_object(storage, previous_key)

    return UploadedPhoto(photo=photo, quality=quality)
