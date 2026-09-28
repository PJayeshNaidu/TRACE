"""Top-level API router for TRACE."""

from trace.api.health.router import health_router

from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(health_router)
