from trace.api.analyses.router import analyses_router
from trace.api.diff.router import diff_router
from trace.api.graph.router import graph_router
from trace.api.health.router import health_router
from trace.api.impact.router import impact_router
from trace.api.planner.router import planner_router
from trace.api.projects.router import projects_router
from trace.api.repositories.router import repositories_router

from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(projects_router, prefix="/api/v1")
api_router.include_router(repositories_router, prefix="/api/v1")
api_router.include_router(analyses_router, prefix="/api/v1")
api_router.include_router(graph_router, prefix="/api/v1")
api_router.include_router(diff_router, prefix="/api/v1")
api_router.include_router(impact_router, prefix="/api/v1")
api_router.include_router(planner_router, prefix="/api/v1")
