from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness-проверка: процесс жив и принимает запросы."""
    return HealthResponse(
        status="ok",
        version=settings.version,
        environment=settings.environment,
    )
