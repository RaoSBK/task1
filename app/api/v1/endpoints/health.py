"""Health check API endpoint."""

from fastapi import APIRouter, status, Response
from app.core.config import settings
from app.database.session import check_database_connection
from app.schemas.health import HealthCheckResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Application and Database Health Check",
    description="Check whether the application is responsive and the PostgreSQL database is reachable.",
    status_code=status.HTTP_200_OK,
)
def get_health(response: Response) -> HealthCheckResponse:
    """Perform health checks on application and PostgreSQL database connection."""
    is_db_connected = check_database_connection()

    if not is_db_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthCheckResponse(
            status="unhealthy",
            environment=settings.ENVIRONMENT,
            database="disconnected",
            version="0.1.0",
        )

    return HealthCheckResponse(
        status="healthy",
        environment=settings.ENVIRONMENT,
        database="connected",
        version="0.1.0",
    )
