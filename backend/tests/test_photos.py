from collections.abc import Iterator
from io import BytesIO
from uuid import UUID, uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Inspection,
    InspectionKind,
    InspectionStatus,
    Organization,
    Photo,
    User,
    UserRole,
    Vehicle,
)
from app.main import app
from app.services.storage import StorageError, StorageService, get_storage

BUCKET = "fleetguard-photos-test"
ALL_SIDES = ["front", "back", "left", "right"]

ADMIN = {
    "organization_name": "Парк А",
    "name": "Админ А",
    "email": "admin@a.example",
    "password": "admin-password",
}


@pytest.fixture
def storage(client: TestClient) -> Iterator[StorageService]:
    # moto подменяет S3 в процессе, поэтому тесты не требуют MinIO.
    with mock_aws():
        service = StorageService(
            bucket=BUCKET,
            access_key="test-key",
            secret_key="test-secret",
            presign_expire_seconds=120,
        )
        service.ensure_bucket()
        app.dependency_overrides[get_storage] = lambda: service
        yield service
        app.dependency_overrides.pop(get_storage, None)


def encode(image: Image.Image, fmt: str = "JPEG") -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, quality=95)
    return buffer.getvalue()


def noise_image(width: int = 800, height: int = 600) -> Image.Image:
    rng = np.random.default_rng(7)
    pixels = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    return Image.fromarray(pixels, mode="RGB")


def solid_image(color: tuple[int, int, int], width: int = 800, height: int = 600) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def register(client: TestClient) -> dict:
    response = client.post("/api/v1/auth/register-org", json=ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


def create_vehicle(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/vehicles", json={"plate": "A123BC", "model": "Kia Rio", "year": 2021}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_inspection(client: TestClient, vehicle_id: str) -> dict:
    response = client.post("/api/v1/inspections", json={"vehicle_id": vehicle_id, "kind": "before"})
    assert response.status_code == 201, response.text
    return response.json()


def upload(
    client: TestClient,
    inspection_id: str,
    data: bytes,
    side: str = "front",
    filename: str = "photo.jpg",
    content_type: str = "image/jpeg",
):
    return client.post(
        f"/api/v1/inspections/{inspection_id}/photos",
        params={"side": side},
        files={"file": (filename, data, content_type)},
    )


def photo_row(db_session: Session, inspection_id: str, side: str = "front") -> Photo:
    db_session.expire_all()
    photo = db_session.scalar(
        select(Photo).where(
            Photo.inspection_id == UUID(inspection_id),
            Photo.side == side,
        )
    )
    assert photo is not None
    return photo


def seed_photos(db_session: Session, inspection_id: str) -> None:
    for side in ALL_SIDES:
        db_session.add(
            Photo(
                inspection_id=UUID(inspection_id),
                side=side,
                storage_key=f"photos/{inspection_id}/{side}.jpg",
                width=1600,
                height=1200,
                quality_score=0.9,
                quality_flags=[],
            )
        )
    db_session.commit()


def make_foreign_inspection(db_session: Session) -> Inspection:
    org = Organization(name="Парк Б")
    user = User(
        organization=org,
        email="admin@b.example",
        password_hash="not-a-real-hash",
        name="Админ Б",
        role=UserRole.admin,
    )
    vehicle = Vehicle(organization=org, plate="B999BB", model="Hyundai Solaris", year=2019)
    db_session.add_all([org, user, vehicle])
    db_session.commit()

    inspection = Inspection(
        org_id=org.id,
        vehicle_id=vehicle.id,
        driver_id=user.id,
        kind=InspectionKind.before,
        pair_id=uuid4(),
        status=InspectionStatus.draft,
    )
    db_session.add(inspection)
    db_session.commit()
    return inspection


def test_upload_sharp_photo_is_accepted(
    client: TestClient, db_session: Session, storage: StorageService
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])

    response = upload(client, inspection["id"], encode(noise_image()))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["side"] == "front"
    assert body["width"] == 800
    assert body["height"] == 600
    assert body["quality"]["ok"] is True
    assert body["quality"]["flags"] == []
    assert body["quality"]["score"] >= 0.9

    photo = photo_row(db_session, inspection["id"])
    assert photo.id == UUID(body["photo_id"])
    assert photo.storage_key.endswith(".jpg")
    # Ключ случайный: по нему нельзя угадать соседние фото.
    assert UUID(inspection["id"]).hex not in photo.storage_key.split("/")[-1]

    stored, content_type = storage.download(photo.storage_key)
    assert content_type == "image/jpeg"
    assert stored.startswith(b"\xff\xd8\xff")


def test_blurry_photo_is_reported_not_rejected(
    client: TestClient, db_session: Session, storage: StorageService
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])

    response = upload(client, inspection["id"], encode(solid_image((128, 128, 128))))

    assert response.status_code == 201, response.text
    quality = response.json()["quality"]
    assert quality["ok"] is False
    assert quality["flags"] == ["blurry"]
    assert quality["score"] < 0.6

    # Фото всё равно сохранено: решение «переснять» принимает фронтенд.
    assert photo_row(db_session, inspection["id"]).quality_flags == ["blurry"]


def test_dark_photo_is_flagged(client: TestClient, storage: StorageService) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])

    body = upload(client, inspection["id"], encode(solid_image((5, 5, 5)))).json()

    assert body["quality"]["ok"] is False
    assert "too_dark" in body["quality"]["flags"]


def test_png_is_stored_as_jpeg(
    client: TestClient, db_session: Session, storage: StorageService
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])

    response = upload(
        client,
        inspection["id"],
        encode(noise_image(), fmt="PNG"),
        filename="photo.png",
        content_type="image/png",
    )

    assert response.status_code == 201, response.text
    photo = photo_row(db_session, inspection["id"])
    stored, content_type = storage.download(photo.storage_key)
    assert content_type == "image/jpeg"
    assert stored.startswith(b"\xff\xd8\xff")


def test_transparent_png_is_flattened_on_white(
    client: TestClient, db_session: Session, storage: StorageService
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])
    transparent = Image.new("RGBA", (800, 600), (0, 0, 0, 0))

    response = upload(client, inspection["id"], encode(transparent, fmt="PNG"), filename="p.png")

    assert response.status_code == 201, response.text
    photo = photo_row(db_session, inspection["id"])
    stored, _ = storage.download(photo.storage_key)
    with Image.open(BytesIO(stored)) as image:
        assert image.mode == "RGB"
        assert image.getpixel((10, 10)) == (255, 255, 255)


def test_exif_orientation_is_applied(
    client: TestClient, db_session: Session, storage: StorageService
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])
    exif = Image.Exif()
    exif[0x0112] = 6  # Поворот на 90° против часовой стрелки.
    buffer = BytesIO()
    noise_image().save(buffer, format="JPEG", quality=95, exif=exif.tobytes())

    response = upload(client, inspection["id"], buffer.getvalue())

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["width"], body["height"]) == (600, 800)
    photo = photo_row(db_session, inspection["id"])
    assert (photo.width, photo.height) == (600, 800)


def test_retake_replaces_object_and_keeps_single_row(
    client: TestClient, db_session: Session, storage: StorageService
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])
    upload(client, inspection["id"], encode(noise_image()))
    first_key = photo_row(db_session, inspection["id"]).storage_key

    response = upload(client, inspection["id"], encode(solid_image((128, 128, 128))))

    assert response.status_code == 201, response.text
    second_key = photo_row(db_session, inspection["id"]).storage_key
    assert second_key != first_key

    # Старый объект удалён, новый на месте.
    with pytest.raises(StorageError):
        storage.download(first_key)
    assert storage.download(second_key)[0].startswith(b"\xff\xd8\xff")

    rows = db_session.scalars(
        select(Photo).where(Photo.inspection_id == UUID(inspection["id"]))
    ).all()
    assert len(rows) == 1


def test_empty_file_is_rejected(client: TestClient, storage: StorageService) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])

    response = upload(client, inspection["id"], b"")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_file"


def test_file_over_limit_is_rejected(
    client: TestClient, storage: StorageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)

    response = upload(client, inspection["id"], b"x" * 2048)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_too_many_pixels_is_rejected(
    client: TestClient, storage: StorageService, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])
    monkeypatch.setattr(settings, "max_image_pixels", 1_000_000)

    response = upload(client, inspection["id"], encode(noise_image(2000, 1000)))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"


def test_non_image_file_is_rejected(client: TestClient, storage: StorageService) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])

    response = upload(client, inspection["id"], b"not an image at all", filename="fake.jpg")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "invalid_image"


def test_gif_is_rejected_by_content_type(client: TestClient, storage: StorageService) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])

    response = upload(client, inspection["id"], encode(noise_image(), fmt="GIF"), filename="p.gif")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_image_type"


def test_finished_inspection_rejects_new_photos(
    client: TestClient, db_session: Session, storage: StorageService
) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])
    seed_photos(db_session, inspection["id"])
    assert client.post(f"/api/v1/inspections/{inspection['id']}/finish").status_code == 202

    response = upload(client, inspection["id"], encode(noise_image()))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inspection_not_draft"


def test_foreign_inspection_returns_404(
    client: TestClient, db_session: Session, storage: StorageService
) -> None:
    register(client)
    foreign = make_foreign_inspection(db_session)

    response = upload(client, str(foreign.id), encode(noise_image()))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "inspection_not_found"


def test_invalid_side_is_rejected(client: TestClient, storage: StorageService) -> None:
    register(client)
    inspection = create_inspection(client, create_vehicle(client)["id"])

    response = upload(client, inspection["id"], encode(noise_image()), side="roof")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_upload_requires_authentication(client: TestClient, storage: StorageService) -> None:
    client.cookies.clear()

    response = upload(client, str(uuid4()), encode(noise_image()))

    assert response.status_code == 401
