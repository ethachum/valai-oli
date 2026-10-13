"""
Valaioli — Job store: thread-safe in-memory job registry.

All mutations go through JobStore methods so the dict is never
accessed directly from multiple coroutines without coordination.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Literal

# ── Job state type ────────────────────────────────────────────────────────────

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

# ── Job record (mutable dataclass-style) ──────────────────────────────────────

class Job:
    """Mutable job record. All attribute writes happen inside the store lock."""

    __slots__ = (
        "job_id", "url", "format_id", "output_format", "title",
        "state", "progress_percent", "message",
        "created_at", "completed_at", "error", "output_path",
        "_cancel_requested", "thumbnail", "start_time", "end_time",
        "channel", "waveform_path", "is_gif",
    )

    def __init__(
        self,
        job_id: str,
        url: str,
        format_id: str,
        output_format: str | None,
        title: str | None = None,
        thumbnail: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        channel: str | None = None,
        is_gif: bool = False,
    ) -> None:
        self.job_id = job_id
        self.url = url
        self.format_id = format_id
        self.output_format = output_format
        self.title = title
        self.thumbnail = thumbnail
        self.start_time = start_time
        self.end_time = end_time
        self.channel = channel
        self.is_gif = is_gif
        self.waveform_path: str | None = None
        self.output_path: str | None = None
        self.state: JobState = "queued"
        self.progress_percent: float | None = 0.0
        self.message: str | None = "Job queued."
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.completed_at: str | None = None
        self.error: str | None = None
        self._cancel_requested: bool = False

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "format_id": self.format_id,
            "output_format": self.output_format,
            "title": self.title,
            "thumbnail": getattr(self, "thumbnail", None),
            "start_time": getattr(self, "start_time", None),
            "end_time": getattr(self, "end_time", None),
            "channel": getattr(self, "channel", None),
            "is_gif": getattr(self, "is_gif", False),
            "waveform_path": getattr(self, "waveform_path", None),
            "state": self.state,
            "progress_percent": self.progress_percent,
            "message": self.message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "output_path": self.output_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        job = cls(
            job_id=data["job_id"],
            url=data.get("url", ""),
            format_id=data.get("format_id", ""),
            output_format=data.get("output_format"),
            title=data.get("title"),
            thumbnail=data.get("thumbnail"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            channel=data.get("channel"),
            is_gif=data.get("is_gif", False),
        )
        job.waveform_path = data.get("waveform_path")
        job.state = data.get("state", "completed")
        job.progress_percent = data.get("progress_percent", 100.0)
        job.message = data.get("message", "Download ready.")
        job.created_at = data.get("created_at", datetime.now(timezone.utc).isoformat())
        job.completed_at = data.get("completed_at")
        job.error = data.get("error")
        job.output_path = data.get("output_path")
        return job


# ── Store ─────────────────────────────────────────────────────────────────────

import json
import logging
from pathlib import Path

_logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PERSISTENCE_FILE = _REPO_ROOT / "staging" / "jobs_store.json"


class JobStore:
    """
    Thread-safe store for Job objects with optional disk persistence.

    Uses a plain RLock so sync routes in FastAPI can also call these methods
    without deadlocking (FastAPI runs sync handlers in a thread pool).
    """

    def __init__(self, persistence_file: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._persistence_file = persistence_file
        if self._persistence_file:
            self._load_from_disk()

    def _save_to_disk(self) -> None:
        if not self._persistence_file:
            return
        try:
            self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
            data = [
                j.to_dict() for j in self._jobs.values()
                if j.state in ("completed", "failed", "cancelled")
            ]
            temp_file = self._persistence_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self._persistence_file)
        except Exception as exc:
            _logger.warning("Failed to save jobs store: %s", exc)

    def _load_from_disk(self) -> None:
        if not self._persistence_file or not self._persistence_file.exists():
            return
        try:
            with open(self._persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "job_id" in item:
                        job = Job.from_dict(item)
                        self._jobs[job.job_id] = job
        except Exception as exc:
            _logger.warning("Failed to load jobs store: %s", exc)

    def restore_jobs(self, jobs_data: list[dict]) -> int:
        restored = 0
        with self._lock:
            for item in jobs_data:
                jid = item.get("job_id")
                if not jid:
                    continue
                if jid not in self._jobs:
                    job = Job.from_dict(item)
                    self._jobs[jid] = job
                    restored += 1
                else:
                    existing = self._jobs[jid]
                    if not existing.title and item.get("title"):
                        existing.title = item.get("title")
                    if not existing.output_path and item.get("output_path"):
                        existing.output_path = item.get("output_path")
            if restored > 0:
                self._save_to_disk()
        return restored

    # ── Creation ──────────────────────────────────────────────────────────────

    def create(
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
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            url=url,
            format_id=format_id,
            output_format=output_format,
            title=title,
            thumbnail=thumbnail,
            start_time=start_time,
            end_time=end_time,
            channel=channel,
            is_gif=is_gif,
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def find_by_url(self, url: str) -> "Job | None":
        """Return the most recent completed job matching the given URL, or None."""
        with self._lock:
            matches = [
                j for j in self._jobs.values()
                if j.url == url and j.state == "completed"
            ]
        if not matches:
            return None
        return max(matches, key=lambda j: j.created_at)


    # ── Reads ─────────────────────────────────────────────────────────────────

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_all(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    # ── Mutations ──────────────────────────────────────────────────────────────

    def update(
        self,
        job_id: str,
        *,
        state: JobState | None = None,
        progress_percent: float | None = None,
        message: str | None = None,
        error: str | None = None,
        completed_at: str | None = None,
        title: str | None = None,
        output_path: str | None = None,
        waveform_path: str | None = None,
    ) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if state is not None:
                job.state = state
            if progress_percent is not None:
                job.progress_percent = progress_percent
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
            if completed_at is not None:
                job.completed_at = completed_at
            if title is not None:
                job.title = title
            if output_path is not None:
                job.output_path = output_path
            if waveform_path is not None:
                job.waveform_path = waveform_path
        return job

    def request_cancel(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job._cancel_requested = True  # noqa: SLF001
            if job.state in ("queued",):
                job.state = "cancelled"
                job.message = "Cancelled by user."
                job.completed_at = datetime.now(timezone.utc).isoformat()
        return job

    def mark_completed(self, job_id: str, output_path: str | None = None) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.state = "completed"
            job.progress_percent = 100.0
            job.message = "Download ready."
            job.completed_at = datetime.now(timezone.utc).isoformat()
            if output_path is not None:
                job.output_path = output_path
            self._save_to_disk()
        return job

    def mark_failed(self, job_id: str, error: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.state = "failed"
            job.error = error
            job.message = f"Failed: {error[:120]}"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            self._save_to_disk()
        return job

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def evict_old(self, max_completed: int = 50) -> None:
        """Remove oldest completed/failed/cancelled jobs beyond max_completed."""
        with self._lock:
            terminal = [
                j for j in self._jobs.values()
                if j.state in ("completed", "failed", "cancelled")
            ]
            terminal.sort(key=lambda j: j.created_at)
            for job in terminal[:-max_completed]:
                del self._jobs[job.job_id]
            self._save_to_disk()

    def remove(self, job_id: str) -> bool:
        """Remove a job by ID from the store."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                self._save_to_disk()
                return True
            return False

    def clear_finished(self) -> int:
        """Remove all completed, failed, or cancelled jobs."""
        with self._lock:
            to_del = [
                jid for jid, j in self._jobs.items()
                if j.state in ("completed", "failed", "cancelled")
            ]
            for jid in to_del:
                del self._jobs[jid]
            if to_del:
                self._save_to_disk()
            return len(to_del)
