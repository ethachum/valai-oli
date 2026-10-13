"""
Valaioli — Download job endpoints

POST   /api/jobs                      Create a new download job
GET    /api/jobs/{job_id}             Get job status and progress
POST   /api/jobs/{job_id}/cancel      Request job cancellation
GET    /api/jobs/{job_id}/download    Stream completed output file
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.jobs import JobService
from app.api._deps import get_job_service

import hashlib
import io
import re
import zipfile

router = APIRouter(tags=["jobs"])

# ── Schemas ───────────────────────────────────────────────────────────────────

JobState = Literal[
    "queued",
    "downloading",
    "merging",
    "converting",
    "validating",
    "completed",
    "failed",
    "cancelled",
    "paused",
]


class JobRequest(BaseModel):
    url: str
    format_id: str
    output_format: str | None = None   # e.g. "mp3", "m4a", "wav", "flac"
    title: str | None = None
    thumbnail: str | None = None
    start_time: str | None = None      # e.g. "0:30" or "00:00:30" — clip start
    end_time: str | None = None        # e.g. "1:45" or "00:01:45" — clip end
    channel: str | None = None
    is_gif: bool = False


class JobStatus(BaseModel):
    job_id: str
    state: JobState
    progress_percent: float | None
    message: str | None
    created_at: str
    completed_at: str | None
    error: str | None
    title: str | None = None
    thumbnail: str | None = None
    url: str | None = None
    format_id: str | None = None
    output_format: str | None = None
    channel: str | None = None
    is_gif: bool | None = False
    waveform_path: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def sanitize_filename(name: str) -> str:
    """
    Sanitize a video title into a safe, friendly filename across OSes (Windows/Mac/Linux).
    Preserves Unicode (Tamil, Japanese, accents, etc.) while stripping illegal filesystem characters.
    """
    cleaned = re.sub(r'[\x00-\x1f*?"<>|]', '', name)
    cleaned = re.sub(r'[/\\:]+', ' - ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'(\s*-\s*)+', ' - ', cleaned)
    cleaned = cleaned.strip('. -')
    if cleaned.upper() in _RESERVED_NAMES:
        cleaned = f"{cleaned}_media"
    return cleaned[:200] or "download"


def _job_to_status(job) -> JobStatus:  # type: ignore[no-untyped-def]
    return JobStatus(**job.to_dict())


def _not_found(job_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/jobs", response_model=JobStatus, status_code=202)
async def create_job(
    request: JobRequest,
    svc: JobService = Depends(get_job_service),
) -> JobStatus:
    """Enqueue a new download job. Returns immediately with state=queued."""
    from app.security.url_validator import UnsupportedURLError
    try:
        job = svc.create_job(
            url=request.url,
            format_id=request.format_id,
            output_format=request.output_format,
            title=request.title,
            thumbnail=request.thumbnail,
            start_time=request.start_time,
            end_time=request.end_time,
            channel=request.channel,
            is_gif=request.is_gif,
        )
    except UnsupportedURLError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _job_to_status(job)


@router.get("/jobs", response_model=list[JobStatus])
async def list_jobs(
    svc: JobService = Depends(get_job_service),
) -> list[JobStatus]:
    """Return all jobs (active and historical) ordered newest-first."""
    jobs = svc.list_jobs()
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return [_job_to_status(j) for j in jobs]


@router.get("/jobs/zip")
async def download_jobs_zip(
    ids: str | None = Query(None, description="Comma-separated list of job IDs. If omitted, packages all completed jobs."),
    title: str | None = Query(None, description="Optional playlist/archive title used as the ZIP filename."),
    svc: JobService = Depends(get_job_service),
):
    """
    Package completed download files into a single ZIP archive and stream to browser.
    """
    from app.jobs.runner import _DOWNLOADS_DIR
    from urllib.parse import quote

    if ids:
        target_ids = [i.strip() for i in ids.split(",") if i.strip()]
    else:
        target_ids = [j.job_id for j in svc.list_jobs() if j.state == "completed"]

    zip_buffer = io.BytesIO()
    added_count = 0
    used_names: set[str] = set()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for job_id in target_ids:
            job = svc.get_job(job_id)
            if job is not None and job.state != "completed":
                continue

            output_path = None
            if job and getattr(job, "output_path", None):
                candidate = Path(job.output_path)
                if candidate.exists() and candidate.stat().st_size > 0:
                    output_path = candidate

            if output_path is None:
                safe_id = hashlib.sha1(job_id.encode()).hexdigest()[:12]
                candidates = list(_DOWNLOADS_DIR.glob(f"{safe_id}.*"))
                if candidates:
                    output_path = max(candidates, key=lambda p: p.stat().st_mtime)

            if output_path and output_path.exists() and output_path.stat().st_size > 0:
                ext = output_path.suffix.lstrip(".")
                raw_title = (getattr(job, "title", None) if job else None) or f"track_{added_count + 1}"
                base_name = sanitize_filename(raw_title)
                clean_name = f"{base_name}.{ext}"
                counter = 2
                while clean_name in used_names:
                    clean_name = f"{base_name} ({counter}).{ext}"
                    counter += 1
                used_names.add(clean_name)

                zf.write(output_path, arcname=clean_name)
                added_count += 1

    if added_count == 0:
        raise HTTPException(
            status_code=404,
            detail="No completed download files found to package into ZIP.",
        )

    zip_buffer.seek(0)
    zip_bytes = zip_buffer.getvalue()

    # Build ZIP filename from the provided title (playlist name) or fallback
    raw_zip_name = sanitize_filename(title) if title and title.strip() else "valaioli_downloads"
    zip_filename = f"{raw_zip_name}.zip"

    # Build Content-Disposition with proper Unicode support (RFC 5987)
    try:
        zip_filename.encode("latin-1")
        disposition = f'attachment; filename="{zip_filename}"'
    except UnicodeEncodeError:
        ascii_fallback = re.sub(r'[^\x20-\x7E]', '_', zip_filename).replace('"', '')
        disposition = f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(zip_filename)}'

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(zip_bytes)),
            "Content-Type": "application/zip",
        },
    )


@router.post("/jobs/sync")
async def sync_jobs(
    jobs: list[dict],
    svc: JobService = Depends(get_job_service),
):
    """
    Import completed/historical jobs from frontend localStorage to ensure
    continuity across backend restarts.
    """
    from app.jobs.runner import _DOWNLOADS_DIR
    for item in jobs:
        jid = item.get("job_id")
        if jid and not item.get("output_path"):
            safe_id = hashlib.sha1(jid.encode()).hexdigest()[:12]
            candidates = list(_DOWNLOADS_DIR.glob(f"{safe_id}.*"))
            if candidates:
                item["output_path"] = str(max(candidates, key=lambda p: p.stat().st_mtime))
    restored = svc.restore_jobs(jobs)
    return {"restored": restored}


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(
    job_id: str,
    svc: JobService = Depends(get_job_service),
) -> JobStatus:
    """Return current job status and progress."""
    job = svc.get_job(job_id)
    if job is None:
        raise _not_found(job_id)
    return _job_to_status(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobStatus)
async def cancel_job(
    job_id: str,
    svc: JobService = Depends(get_job_service),
) -> JobStatus:
    """Request cooperative cancellation of a running job."""
    job = svc.cancel_job(job_id)
    if job is None:
        raise _not_found(job_id)
    return _job_to_status(job)


@router.post("/jobs/{job_id}/pause", response_model=JobStatus)
async def pause_job(
    job_id: str,
    svc: JobService = Depends(get_job_service),
) -> JobStatus:
    """Pause a running download job."""
    job = svc.pause_job(job_id)
    if job is None:
        raise _not_found(job_id)
    return _job_to_status(job)


@router.post("/jobs/{job_id}/resume", response_model=JobStatus)
async def resume_job(
    job_id: str,
    svc: JobService = Depends(get_job_service),
) -> JobStatus:
    """Resume a paused download job."""
    job = svc.resume_job(job_id)
    if job is None:
        raise _not_found(job_id)
    return _job_to_status(job)


@router.post("/jobs/{job_id}/retry", response_model=JobStatus, status_code=202)
async def retry_job(
    job_id: str,
    svc: JobService = Depends(get_job_service),
) -> JobStatus:
    """Retry a failed or cancelled job by re-enqueuing it."""
    old_job = svc.get_job(job_id)
    if old_job is None:
        raise _not_found(job_id)

    # Re-create and launch the job with the same parameters
    new_job = svc.create_job(
        url=old_job.url,
        format_id=old_job.format_id,
        output_format=old_job.output_format,
        title=old_job.title,
        thumbnail=old_job.thumbnail,
        start_time=getattr(old_job, 'start_time', None),
        end_time=getattr(old_job, 'end_time', None),
        channel=getattr(old_job, 'channel', None),
        is_gif=getattr(old_job, 'is_gif', False),
    )
    # Remove the old failed entry
    svc.remove_job(job_id)
    return _job_to_status(new_job)



@router.get("/jobs/{job_id}/download")
@router.get("/jobs/{job_id}/download/{filename:path}")
async def download_job(
    job_id: str,
    filename: str | None = None,
    svc: JobService = Depends(get_job_service),
):
    """
    Stream the completed output file to the browser with the video title as filename.

    Returns 409 if the job is not yet completed.
    Returns 410 if the output file has been evicted.
    """
    job = svc.get_job(job_id)
    if job is not None and job.state != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed (state={job.state!r}).",
        )

    # Find the output file
    output_path = None
    if job and getattr(job, "output_path", None):
        candidate = Path(job.output_path)
        if candidate.exists() and candidate.stat().st_size > 0:
            output_path = candidate

    if output_path is None:
        from app.jobs.runner import _DOWNLOADS_DIR
        safe_id = hashlib.sha1(job_id.encode()).hexdigest()[:12]
        candidates = [
            p for p in _DOWNLOADS_DIR.glob(f"**/{safe_id}.*")
            if not p.name.endswith(".wave.png")
        ]
        if not candidates:
            if job is None:
                raise _not_found(job_id)
            raise HTTPException(
                status_code=410,
                detail="Output file no longer available. Re-submit the download request.",
            )
        output_path = max(candidates, key=lambda p: p.stat().st_mtime)

    # Derive download filename from YouTube title
    ext = output_path.suffix.lstrip(".")
    raw_name = filename or (getattr(job, "title", None) if job else None)
    if raw_name:
        clean_title = sanitize_filename(Path(raw_name).stem if filename else raw_name)
    else:
        clean_title = "download"
    download_filename = f"{clean_title}.{ext}"

    from urllib.parse import quote
    try:
        download_filename.encode("latin-1")
        disposition = f'attachment; filename="{download_filename}"'
    except UnicodeEncodeError:
        ascii_fallback = re.sub(r'[^\x20-\x7E]', '_', download_filename).replace('"', '')
        disposition = f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(download_filename)}\'\''

    return FileResponse(
        path=str(output_path),
        filename=download_filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    svc: JobService = Depends(get_job_service),
):
    """Remove a job entry from history. Active jobs are cancelled first."""
    removed = svc.remove_job(job_id)
    if not removed:
        raise _not_found(job_id)


@router.get("/jobs/{job_id}/waveform")
async def get_job_waveform(
    job_id: str,
    svc: JobService = Depends(get_job_service),
):
    """Serve the waveform visualization PNG for an audio job, if generated."""
    job = svc.get_job(job_id)
    wave_path = getattr(job, "waveform_path", None) if job else None

    if wave_path and Path(wave_path).exists() and Path(wave_path).stat().st_size > 0:
        return FileResponse(path=str(wave_path), media_type="image/png")

    # Fallback: search _DOWNLOADS_DIR for {safe_id}.wave.png
    from app.jobs.runner import _DOWNLOADS_DIR
    safe_id = hashlib.sha1(job_id.encode()).hexdigest()[:12]
    matches = list(_DOWNLOADS_DIR.glob(f"**/{safe_id}.wave.png"))
    if matches and matches[0].stat().st_size > 0:
        return FileResponse(path=str(matches[0]), media_type="image/png")

    raise HTTPException(status_code=404, detail="Waveform not available for this job.")


@router.delete("/jobs", status_code=200)
async def clear_jobs(
    svc: JobService = Depends(get_job_service),
):
    """Remove all completed, failed, and cancelled jobs from history."""
    count = svc.clear_finished()
    return {"cleared": count}
