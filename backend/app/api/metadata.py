"""
Valaioli — POST /api/metadata

Accepts a YouTube URL, validates it, extracts metadata via yt-dlp,
and returns available media formats.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.jobs import JobService, ToolsNotReadyError
from app.media.ytdlp import YtDlpError, VideoMetadata
from app.security.url_validator import UnsupportedURLError
from app.api._deps import get_job_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metadata"])


# ── Request / Response schemas ────────────────────────────────────────────────

class MetadataRequest(BaseModel):
    url: str


class FormatInfo(BaseModel):
    format_id: str
    ext: str
    resolution: str | None
    vcodec: str | None
    acodec: str | None
    filesize_approx: int | None
    has_video: bool
    has_audio: bool
    note: str | None


class MetadataResponse(BaseModel):
    title: str
    thumbnail: str | None
    duration_seconds: int | None
    uploader: str | None
    formats: list[FormatInfo]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/metadata", response_model=MetadataResponse)
async def get_metadata(
    request: MetadataRequest,
    svc: JobService = Depends(get_job_service),
) -> MetadataResponse:
    """
    Validate a YouTube URL and return available media formats and metadata.
    """
    try:
        meta: VideoMetadata = await svc.fetch_metadata(request.url)
    except ToolsNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnsupportedURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except YtDlpError as exc:
        raise HTTPException(status_code=502, detail=f"yt-dlp error: {exc}") from exc
    except Exception as exc:
        logger.exception("Unhandled error in get_metadata: %s", exc)
        raise HTTPException(status_code=500, detail=f"Server error: {exc}") from exc

    return MetadataResponse(
        title=meta.title,
        thumbnail=meta.thumbnail,
        duration_seconds=meta.duration_seconds,
        uploader=meta.uploader,
        formats=[
            FormatInfo(
                format_id=f.format_id,
                ext=f.ext,
                resolution=f.resolution,
                vcodec=f.vcodec,
                acodec=f.acodec,
                filesize_approx=f.filesize_approx,
                has_video=f.has_video,
                has_audio=f.has_audio,
                note=f.note,
            )
            for f in meta.formats
        ],
    )
