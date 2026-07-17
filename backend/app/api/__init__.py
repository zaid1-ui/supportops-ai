"""API routers (Part 10)."""

from fastapi import APIRouter

from backend.app.api import agents, approvals, auth, documents, metrics, workflows

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(agents.router)
api_router.include_router(documents.router)
api_router.include_router(workflows.router)
api_router.include_router(approvals.router)
api_router.include_router(metrics.router)

__all__ = ["api_router"]
