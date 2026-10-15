"""Main FastAPI application entrypoint."""

from fastapi import FastAPI, Response, status
from app.core.config import settings
from app.api.v1.router import api_router
from app.database.session import check_database_connection
from app.schemas.health import HealthCheckResponse


def create_application() -> FastAPI:
    """Application factory for Customer Support Ticket Management System."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Backend API for Customer Support Ticket Management System",
        version="0.1.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
    )

    # Root health check endpoint for container orchestrators / load balancers
    @app.get(
        "/health",
        response_model=HealthCheckResponse,
        summary="Root Health Check",
        tags=["Health"],
        status_code=status.HTTP_200_OK,
    )
    def root_health(response: Response) -> HealthCheckResponse:
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

    # Include versioned API router
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Root route alias for /tickets
    from app.api.v1.endpoints import tickets
    app.include_router(tickets.router, prefix="/tickets", tags=["Tickets (Root Alias)"])

    return app


app = create_application()
