"""
Valaioli — Playlist endpoints:
- POST /api/playlist/metadata: Retrieve flat playlist metadata and entries
- POST /api/playlist/jobs: Enqueue selected playlist entries for sequential download
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.jobs import JobService, ToolsNotReadyError
from app.media.ytdlp import YtDlpError
from app.security.url_validator import UnsupportedURLError
from app.api._deps import get_job_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["playlist"])


# ── Preset definitions ────────────────────────────────────────────────────────

QUALITY_PRESETS = {
    "1080p": {
        "format_id": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "output_format": "mp4",
        "label": "Full HD 1080p (MP4)",
    },
    "720p": {
        "format_id": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "output_format": "mp4",
        "label": "HD 720p (MP4)",
    },
    "480p": {
        "format_id": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "output_format": "mp4",
        "label": "SD 480p (MP4)",
    },
    "best": {
        "format_id": "bestvideo+bestaudio/best",
        "output_format": "mp4",
        "label": "Highest Available Quality (MP4)",
    },
    "mp3": {
        "format_id": "bestaudio/mp3",
        "output_format": "mp3",
        "label": "Audio Only — MP3 (192 kbps)",
    },
    "m4a": {
        "format_id": "bestaudio/m4a",
        "output_format": "m4a",
        "label": "Audio Only — M4A (AAC)",
    },
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class PlaylistMetadataRequest(BaseModel):
    url: str


class PlaylistItem(BaseModel):
    index: int
    video_id: str
    title: str
    thumbnail: str | None = None
    duration_seconds: int | None = None
    url: str


class PlaylistMetadataResponse(BaseModel):
    playlist_id: str
    title: str
    uploader: str | None = None
    entry_count: int
    entries: list[PlaylistItem]


class PlaylistEnqueueItem(BaseModel):
    index: int
    title: str
    url: str
    thumbnail: str | None = None


class PlaylistJobsRequest(BaseModel):
    items: list[PlaylistEnqueueItem]
    preset: str = "1080p"  # "1080p" | "720p" | "480p" | "best" | "mp3" | "m4a"
    format_id: str | None = None
    output_format: str | None = None


class PlaylistJobsResponse(BaseModel):
    enqueued_count: int
    job_ids: list[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/playlist/metadata", response_model=PlaylistMetadataResponse)
async def get_playlist_metadata(
    request: PlaylistMetadataRequest,
    svc: JobService = Depends(get_job_service),
) -> PlaylistMetadataResponse:
    """Extract flat playlist entries without downloading individual video pages."""
    try:
        meta = await svc.fetch_playlist_metadata(request.url)
    except ToolsNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnsupportedURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except YtDlpError as exc:
        raise HTTPException(status_code=502, detail=f"yt-dlp error: {exc}") from exc
    except Exception as exc:
        logger.exception("Unhandled error in get_playlist_metadata: %s", exc)
        raise HTTPException(status_code=500, detail=f"Server error: {exc}") from exc

    return PlaylistMetadataResponse(
        playlist_id=meta.playlist_id,
        title=meta.title,
        uploader=meta.uploader,
        entry_count=meta.entry_count,
        entries=[
            PlaylistItem(
                index=e.index,
                video_id=e.video_id,
                title=e.title,
                thumbnail=e.thumbnail,
                duration_seconds=e.duration_seconds,
                url=e.url,
            )
            for e in meta.entries
        ],
    )


@router.post("/playlist/jobs", response_model=PlaylistJobsResponse, status_code=202)
async def create_playlist_jobs(
    request: PlaylistJobsRequest,
    svc: JobService = Depends(get_job_service),
) -> PlaylistJobsResponse:
    """
    Queue selected playlist items for sequential downloading with numbered filenames.
    """
    if not request.items:
        raise HTTPException(status_code=422, detail="No playlist items provided.")

    # Resolve preset if explicit format_id not provided
    if request.format_id:
        format_id = request.format_id
        output_format = request.output_format or "mp4"
    else:
        preset_info = QUALITY_PRESETS.get(request.preset, QUALITY_PRESETS["1080p"])
        format_id = preset_info["format_id"]
        output_format = preset_info["output_format"]

    items_data = [
        {
            "index": item.index,
            "title": item.title,
            "url": item.url,
            "thumbnail": item.thumbnail,
        }
        for item in request.items
    ]

    try:
        jobs = svc.create_playlist_jobs(
            items=items_data,
            format_id=format_id,
            output_format=output_format,
        )
    except UnsupportedURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to enqueue playlist jobs: %s", exc)
        raise HTTPException(status_code=500, detail=f"Queue error: {exc}") from exc

    return PlaylistJobsResponse(
        enqueued_count=len(jobs),
        job_ids=[j.job_id for j in jobs],
    )
