from trace.api.health.router import health_router
from trace.api.projects.router import projects_router
from trace.api.repositories.router import repositories_router

from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(projects_router, prefix="/api/v1")
api_router.include_router(repositories_router, prefix="/api/v1")
