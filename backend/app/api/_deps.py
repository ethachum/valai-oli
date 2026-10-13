"""
Valaioli — FastAPI dependency injection helpers.

Provides Depends() callables that read singletons from app.state.
"""
from __future__ import annotations

from fastapi import Request

from app.jobs import JobService
from app.services.manifest import ManifestService


def get_manifest_service(request: Request) -> ManifestService:
    """Inject the application-wide ManifestService from app.state with lazy fallback."""
    if not hasattr(request.app.state, "manifest_service") or request.app.state.manifest_service is None:
        request.app.state.manifest_service = ManifestService()
    return request.app.state.manifest_service  # type: ignore[no-any-return]


def get_job_service(request: Request) -> JobService:
    """Inject the application-wide JobService from app.state with lazy fallback."""
    if not hasattr(request.app.state, "job_service") or request.app.state.job_service is None:
        manifest = get_manifest_service(request)
        request.app.state.job_service = JobService(manifest)
    return request.app.state.job_service  # type: ignore[no-any-return]
