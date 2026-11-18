from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import boto3
from botocore.client import BaseClient, Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

# Нижняя граница SigV4 — 1 минута, верхняя — 7 суток (ограничение AWS).
MIN_PRESIGN_SECONDS: Final = 60
MAX_PRESIGN_SECONDS: Final = 7 * 24 * 60 * 60

_BUCKET_MISSING_CODES: Final = frozenset({"404", "NoSuchBucket", "NotFound"})
_OBJECT_MISSING_CODES: Final = frozenset({"404", "NoSuchKey", "NotFound"})
_BUCKET_EXISTS_CODES: Final = frozenset({"BucketAlreadyOwnedByYou", "BucketAlreadyExists"})


class StorageError(RuntimeError):
    """Ошибка хранилища с машинным кодом для API-слоя."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    content_type: str


def _client_error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _validate_key(key: str) -> None:
    # Ключи строит сервер, но защита от «..» и абсолютных путей стоит дёшево.
    segments = key.split("/")
    if not key or "\\" in key or any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("Некорректный ключ объекта в хранилище")


def _build_client(
    *,
    endpoint_url: str | None,
    access_key: str,
    secret_key: str,
    region: str,
    use_ssl: bool,
) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        use_ssl=use_ssl,
        config=Config(
            signature_version="s3v4",
            # Path-style обязателен для MinIO: иначе bucket.localhost не резолвится.
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=10,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


class StorageService:
    """Обёртка над S3 API: загрузка, чтение, удаление и подписанные ссылки.

    Бакет считается приватным: наружу отдаются только presigned URL с коротким сроком.
    """

    def __init__(
        self,
        *,
        bucket: str,
        access_key: str,
        secret_key: str,
        endpoint_url: str | None = None,
        public_endpoint_url: str | None = None,
        region: str = "us-east-1",
        use_ssl: bool = False,
        presign_expire_seconds: int = 900,
        client: BaseClient | None = None,
    ) -> None:
        if not MIN_PRESIGN_SECONDS <= presign_expire_seconds <= MAX_PRESIGN_SECONDS:
            raise ValueError(
                f"Срок подписанной ссылки должен быть от {MIN_PRESIGN_SECONDS} "
                f"до {MAX_PRESIGN_SECONDS} секунд"
            )
        self.bucket = bucket
        self.region = region
        self.presign_expire_seconds = presign_expire_seconds
        client_kwargs = {
            "access_key": access_key,
            "secret_key": secret_key,
            "region": region,
            "use_ssl": use_ssl,
        }
        self._client = client or _build_client(endpoint_url=endpoint_url, **client_kwargs)
        # Подпись считается локально, поэтому ссылка может вести на внешний адрес MinIO.
        self._presign_client = (
            self._client
            if client is not None or (public_endpoint_url or endpoint_url) == endpoint_url
            else _build_client(endpoint_url=public_endpoint_url or endpoint_url, **client_kwargs)
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as exc:
            if _client_error_code(exc) not in _BUCKET_MISSING_CODES:
                raise StorageError("storage_unavailable", "Хранилище недоступно") from exc
        except BotoCoreError as exc:
            raise StorageError("storage_unavailable", "Хранилище недоступно") from exc

        create_kwargs: dict[str, object] = {"Bucket": self.bucket}
        if self.region != "us-east-1":
            # AWS требует LocationConstraint для любого региона, кроме us-east-1.
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        try:
            self._client.create_bucket(**create_kwargs)
        except ClientError as exc:
            if _client_error_code(exc) not in _BUCKET_EXISTS_CODES:
                raise StorageError("storage_unavailable", "Не удалось создать бакет") from exc
        except BotoCoreError as exc:
            raise StorageError("storage_unavailable", "Не удалось создать бакет") from exc

    def upload(self, key: str, data: bytes, content_type: str) -> StoredObject:
        _validate_key(key)
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("storage_unavailable", "Не удалось сохранить файл") from exc
        return StoredObject(key=key, size=len(data), content_type=content_type)

    def download(self, key: str) -> tuple[bytes, str]:
        _validate_key(key)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if _client_error_code(exc) in _OBJECT_MISSING_CODES:
                raise StorageError("object_not_found", "Файл не найден") from exc
            raise StorageError("storage_unavailable", "Хранилище недоступно") from exc
        except BotoCoreError as exc:
            raise StorageError("storage_unavailable", "Хранилище недоступно") from exc

        body: bytes = response["Body"].read()
        content_type = str(response.get("ContentType", "application/octet-stream"))
        return body, content_type

    def delete(self, key: str) -> None:
        _validate_key(key)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("storage_unavailable", "Не удалось удалить файл") from exc

    def presigned_get_url(self, key: str, expires_in: int | None = None) -> str:
        _validate_key(key)
        seconds = self.presign_expire_seconds if expires_in is None else expires_in
        if not MIN_PRESIGN_SECONDS <= seconds <= MAX_PRESIGN_SECONDS:
            raise ValueError(
                f"Срок подписанной ссылки должен быть от {MIN_PRESIGN_SECONDS} "
                f"до {MAX_PRESIGN_SECONDS} секунд"
            )
        try:
            url: str = self._presign_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("storage_unavailable", "Не удалось подписать ссылку") from exc
        return url


@lru_cache
def get_storage() -> StorageService:
    """Единственный клиент S3 на процесс: создаётся при первом обращении."""
    return StorageService(
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        endpoint_url=settings.s3_endpoint_url or None,
        public_endpoint_url=settings.s3_public_endpoint_url or None,
        region=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
        presign_expire_seconds=settings.s3_presign_expire_seconds,
    )
