from collections.abc import Iterator

import pytest
from moto import mock_aws

from app.services.storage import StorageError, StorageService

BUCKET = "fleetguard-test"
KEY = "photos/org-1/inspection-1/front.jpg"
PAYLOAD = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


@pytest.fixture
def storage() -> Iterator[StorageService]:
    # moto подменяет S3 API в процессе: MinIO для тестов не нужен.
    # Кастомный endpoint_url moto не перехватывает, поэтому здесь адрес по умолчанию.
    with mock_aws():
        service = StorageService(
            bucket=BUCKET,
            access_key="test-key",
            secret_key="test-secret",
            presign_expire_seconds=120,
        )
        service.ensure_bucket()
        yield service


def test_upload_and_download_roundtrip(storage: StorageService) -> None:
    stored = storage.upload(KEY, PAYLOAD, "image/jpeg")

    assert stored.key == KEY
    assert stored.size == len(PAYLOAD)

    body, content_type = storage.download(KEY)
    assert body == PAYLOAD
    assert content_type == "image/jpeg"


def test_ensure_bucket_is_idempotent(storage: StorageService) -> None:
    storage.ensure_bucket()
    storage.ensure_bucket()


def test_presigned_url_is_signed_with_configured_ttl(storage: StorageService) -> None:
    url = storage.presigned_get_url(KEY)

    assert url.startswith("http")
    assert "front.jpg" in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=120" in url


def test_presigned_url_uses_public_endpoint() -> None:
    service = StorageService(
        bucket=BUCKET,
        access_key="test-key",
        secret_key="test-secret",
        endpoint_url="http://minio:9000",
        public_endpoint_url="http://localhost:9000",
        presign_expire_seconds=120,
    )

    url = service.presigned_get_url(KEY)

    # Браузер не резолвит minio:9000 из docker-сети — ссылка должна вести на внешний адрес.
    assert url.startswith(f"http://localhost:9000/{BUCKET}/")
    assert "X-Amz-Signature=" in url


def test_download_missing_object_raises_storage_error(storage: StorageService) -> None:
    with pytest.raises(StorageError) as exc_info:
        storage.download("photos/missing.jpg")

    assert exc_info.value.code == "object_not_found"


@pytest.mark.parametrize(
    "key",
    ["", "../secret", "/absolute/path", "photos//front.jpg", "photos\\front.jpg"],
)
def test_invalid_keys_are_rejected(storage: StorageService, key: str) -> None:
    with pytest.raises(ValueError):
        storage.upload(key, PAYLOAD, "image/jpeg")


@pytest.mark.parametrize("expires_in", [59, 7 * 24 * 60 * 60 + 1])
def test_presign_ttl_outside_sigv4_bounds_is_rejected(
    storage: StorageService, expires_in: int
) -> None:
    with pytest.raises(ValueError):
        storage.presigned_get_url(KEY, expires_in=expires_in)


def test_constructor_rejects_invalid_default_ttl() -> None:
    with pytest.raises(ValueError):
        StorageService(
            bucket=BUCKET,
            access_key="test-key",
            secret_key="test-secret",
            presign_expire_seconds=10,
        )
