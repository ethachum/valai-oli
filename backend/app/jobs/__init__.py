"""
Valaioli — JobService: facade over JobStore + JobRunner.

The FastAPI app creates one JobService instance in its lifespan context
and stores it as app.state.job_service. API handlers access it via Depends.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.jobs.store import Job, JobStore, _PERSISTENCE_FILE
from app.jobs.runner import JobRunner
from app.media.ytdlp import YtDlpRunner
from app.media.ffmpeg import FfmpegRunner
from app.services.manifest import ManifestService

logger = logging.getLogger(__name__)


class JobService:
    """
    Application-level service that owns the job store and launches runner tasks.

    Tools are resolved lazily: if the manifest has no active version yet,
    enqueuing a job will still succeed but the runner will immediately fail
    with a clear "tools not installed" message.
    """

    def __init__(self, manifest: ManifestService) -> None:
        self._manifest = manifest
        self._store = JobStore(persistence_file=_PERSISTENCE_FILE)
        self._tasks: dict[str, asyncio.Task] = {}
        self._runners: dict[str, JobRunner] = {}

    # ── Tool resolution ───────────────────────────────────────────────────────

    def _get_ytdlp(self) -> YtDlpRunner | None:
        try:
            path = self._manifest.get_ytdlp_path()
        except FileNotFoundError:
            return None
        return YtDlpRunner(path) if path else None

    def _get_ffmpeg(self) -> FfmpegRunner | None:
        try:
            path = self._manifest.get_ffmpeg_path()
        except FileNotFoundError:
            return None
        return FfmpegRunner(path) if path else None

    # ── Job management ────────────────────────────────────────────────────────

    def create_job(
        self,
        url: str,
        format_id: str,
        output_format: str | None = None,
        title: str | None = None,
        thumbnail: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        channel: str | None = None,
        is_gif: bool = False,
    ) -> Job:
        """Create and enqueue a download job. Returns immediately."""
        from app.security.url_validator import validate_youtube_url, UnsupportedURLError
        try:
            canonical_url = validate_youtube_url(url)
        except UnsupportedURLError as e:
            # We fail the job immediately instead of raising HTTP 422 if we want,
            # but wait, the API endpoint is better off returning 422.
            # Let's raise the exception so the API endpoint can catch it and return 422.
            raise e

        job = self._store.create(
            url=canonical_url,
            format_id=format_id,
            output_format=output_format,
            title=title,
            thumbnail=thumbnail,
            start_time=start_time,
            end_time=end_time,
            channel=channel,
            is_gif=is_gif,
        )

        ytdlp = self._get_ytdlp()
        ffmpeg = self._get_ffmpeg()

        if ytdlp is None:
            # Tools not installed yet — fail immediately with a clear message
            self._store.mark_failed(
                job.job_id,
                "yt-dlp is not installed. Run the dependency updater to install media tools.",
            )
            return self._store.get(job.job_id) or job

        runner = JobRunner(
            job=job,
            store=self._store,
            ytdlp=ytdlp,
            ffmpeg=ffmpeg,
        )

        self._runners[job.job_id] = runner
        task = asyncio.create_task(runner.run(), name=f"job-{job.job_id[:8]}")
        self._tasks[job.job_id] = task

        def _cleanup(_):
            self._tasks.pop(job.job_id, None)
            self._runners.pop(job.job_id, None)

        task.add_done_callback(_cleanup)

        return job

    def get_job(self, job_id: str) -> Job | None:
        return self._store.get(job_id)

    def pause_job(self, job_id: str) -> Job | None:
        """Pause a running download job."""
        runner = self._runners.get(job_id)
        if runner:
            runner.pause()
        return self._store.get(job_id)

    def resume_job(self, job_id: str) -> Job | None:
        """Resume a paused download job."""
        runner = self._runners.get(job_id)
        if runner:
            runner.resume()
        return self._store.get(job_id)

    def cancel_job(self, job_id: str) -> Job | None:
        """Request cooperative cancellation; returns updated job record."""
        runner = self._runners.get(job_id)
        if runner:
            runner.cancel()
        job = self._store.request_cancel(job_id)
        # Also cancel the asyncio Task if it's still running
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
        return job

    def list_jobs(self) -> list[Job]:
        return self._store.list_all()

    def remove_job(self, job_id: str) -> bool:
        """Remove a terminal job from history. Active jobs must be cancelled first."""
        job = self._store.get(job_id)
        if job is None:
            return False
        if job.state not in ("completed", "failed", "cancelled"):
            # Cancel active job then remove
            self.cancel_job(job_id)
        return self._store.remove(job_id)

    def clear_finished(self) -> int:
        """Remove all completed/failed/cancelled jobs from history."""
        return self._store.clear_finished()

    def restore_jobs(self, jobs_data: list[dict]) -> int:
        """Import completed/historical jobs into store."""
        return self._store.restore_jobs(jobs_data)

    # ── Metadata (delegates to YtDlpRunner directly) ─────────────────────────

    async def fetch_metadata(self, url: str):  # type: ignore[return]
        """
        Fetch video metadata. Raises ToolsNotReadyError if yt-dlp is missing,
        UnsupportedURLError for bad URLs, YtDlpError for yt-dlp failures.
        """
        ytdlp = self._get_ytdlp()
        if ytdlp is None:
            raise ToolsNotReadyError(
                "yt-dlp is not installed. Use the dependency updater to install media tools "
                "before fetching metadata."
            )
        from app.security.url_validator import validate_youtube_url
        canonical = validate_youtube_url(url)
        return await ytdlp.fetch_metadata(canonical)

    async def fetch_playlist_metadata(self, url: str):  # type: ignore[return]
        """
        Fetch flat playlist metadata. Raises ToolsNotReadyError if yt-dlp is missing,
        UnsupportedURLError for bad URLs, YtDlpError for yt-dlp failures.
        """
        ytdlp = self._get_ytdlp()
        if ytdlp is None:
            raise ToolsNotReadyError(
                "yt-dlp is not installed. Use the dependency updater to install media tools "
                "before fetching playlist metadata."
            )
        from app.security.url_validator import validate_playlist_url
        canonical, _ = validate_playlist_url(url)
        return await ytdlp.fetch_playlist_metadata(canonical)

    def create_playlist_jobs(
        self,
        items: list[dict],
        format_id: str,
        output_format: str | None = None,
    ) -> list[Job]:
        """
        Create and enqueue a batch of playlist items for parallel downloading.
        Returns the created Job instances immediately in 'queued' state.
        Each item gets its own asyncio Task / yt-dlp subprocess and runs concurrently.
        """
        from app.security.url_validator import validate_youtube_url

        jobs: list[Job] = []
        for item in items:
            raw_url = item["url"]
            canonical_url = validate_youtube_url(raw_url)
            raw_title = item.get("title") or "video"
            idx = item.get("index")
            if idx is not None:
                title = f"{int(idx):02d} - {raw_title}"
            else:
                title = raw_title

            job = self._store.create(
                url=canonical_url,
                format_id=format_id,
                output_format=output_format,
                title=title,
                thumbnail=item.get("thumbnail"),
            )
            jobs.append(job)

        ytdlp = self._get_ytdlp()
        ffmpeg = self._get_ffmpeg()

        for job in jobs:
            if ytdlp is None:
                self._store.mark_failed(job.job_id, "yt-dlp is not installed.")
                continue

            runner = JobRunner(job=job, store=self._store, ytdlp=ytdlp, ffmpeg=ffmpeg)
            self._runners[job.job_id] = runner
            task = asyncio.create_task(runner.run(), name=f"job-{job.job_id[:8]}")
            self._tasks[job.job_id] = task

            def _cleanup(_, jid=job.job_id):
                self._tasks.pop(jid, None)
                self._runners.pop(jid, None)

            task.add_done_callback(_cleanup)

        return jobs


    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Cancel all running tasks on server shutdown."""
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        logger.info("JobService shut down; %d tasks cancelled.", len(self._tasks))


class ToolsNotReadyError(RuntimeError):
    """Raised when a required media tool is not yet installed."""
