import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_jwt_secret_must_be_long_enough() -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret="too-short")
