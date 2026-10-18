import logging
from fastapi import FastAPI, Response, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from app.core.config import settings
from app.api.v1.router import api_router
from app.database.session import check_database_connection
from app.schemas.health import HealthCheckResponse

logger = logging.getLogger("app.main")


def create_application() -> FastAPI:
    """Application factory for Customer Support Ticket Management System."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=(
            "Backend API for Customer Support Ticket Management System "
            "supporting role-based access control, ticket lifecycle tracking, "
            "comments, and administrative analytics."
        ),
        version="1.0.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Global unhandled exception handler to prevent leaking internal stack traces or SQL details
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            f"Unhandled server error on {request.method} {request.url.path}: {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred. Please contact system support."},
        )

    # Compatibility redirects for versioned docs endpoints
    @app.get(f"{settings.API_V1_STR}/docs", include_in_schema=False)
    def api_v1_docs_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get(f"{settings.API_V1_STR}/openapi.json", include_in_schema=False)
    def api_v1_openapi_redirect() -> RedirectResponse:
        return RedirectResponse(url="/openapi.json")

    @app.get(f"{settings.API_V1_STR}/redoc", include_in_schema=False)
    def api_v1_redoc_redirect() -> RedirectResponse:
        return RedirectResponse(url="/redoc")

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
    from app.api.v1.endpoints import tickets, analytics
    app.include_router(tickets.router, prefix="/tickets", tags=["Tickets (Root Alias)"])
    app.include_router(analytics.router, prefix="/analytics", tags=["Analytics (Root Alias)"])

    return app


app = create_application()
