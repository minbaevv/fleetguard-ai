import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_jwt_secret_must_be_long_enough() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret="too-short")


@pytest.mark.parametrize("value", [59, 7 * 24 * 60 * 60 + 1])
def test_presign_ttl_must_fit_sigv4_bounds(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret="x" * 40, s3_presign_expire_seconds=value)
