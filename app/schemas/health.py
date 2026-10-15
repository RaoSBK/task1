"""Health check response schemas."""

from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    """Payload returned by the application health check endpoint."""
    status: str = Field(..., description="Overall service status (e.g. 'healthy')")
    environment: str = Field(..., description="Current running environment")
    database: str = Field(..., description="Database connectivity status (e.g. 'connected')")
    version: str = Field("0.1.0", description="Application version")
