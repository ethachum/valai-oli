"""
Valaioli — GET /api/health

Returns application health status. Used by load balancers, monitoring, and
the frontend status display.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return service health and version."""
    return HealthResponse(status="ok", version="0.1.0")
