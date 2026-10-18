"""API v1 master router."""

from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, tickets, analytics

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
