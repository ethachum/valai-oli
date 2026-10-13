"""
Valaioli — GET /api/tools

Reports active media-tool versions resolved from the manifest.
Never exposes filesystem paths or allows modification of dependencies.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.manifest import ManifestService
from app.api._deps import get_manifest_service

router = APIRouter(tags=["tools"])


class ToolInfo(BaseModel):
    name: str
    active_version: str | None
    last_check_utc: str | None
    last_outcome: str | None


class ToolsResponse(BaseModel):
    tools: list[ToolInfo]


@router.get("/tools", response_model=ToolsResponse)
async def tools(
    manifest: ManifestService = Depends(get_manifest_service),
) -> ToolsResponse:
    """Return active dependency versions from the manifest."""
    try:
        versions = manifest.get_versions()
    except FileNotFoundError:
        # Manifest not yet created — return not-checked state gracefully
        return ToolsResponse(
            tools=[
                ToolInfo(name="yt-dlp",  active_version=None, last_check_utc=None, last_outcome="not-checked"),
                ToolInfo(name="ffmpeg", active_version=None, last_check_utc=None, last_outcome="not-checked"),
            ]
        )

    yt = versions.get("ytDlp", {})
    ff = versions.get("ffmpeg", {})
    return ToolsResponse(
        tools=[
            ToolInfo(
                name="yt-dlp",
                active_version=yt.get("activeVersion"),
                last_check_utc=yt.get("lastCheckUtc"),
                last_outcome=yt.get("lastOutcome") or "not-checked",
            ),
            ToolInfo(
                name="ffmpeg",
                active_version=ff.get("activeVersion"),
                last_check_utc=ff.get("lastCheckUtc"),
                last_outcome=ff.get("lastOutcome") or "not-checked",
            ),
        ]
    )
