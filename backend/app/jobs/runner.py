"""
Valaioli — Download job runner (Stage 3).

Orchestrates: validate URL → fetch metadata → download → merge/convert → validate → complete.
Runs as an asyncio background task per job.
All subprocess calls go through YtDlpRunner and FfmpegRunner — never shell=True.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.jobs.store import Job, JobStore
from app.media.ytdlp import YtDlpRunner, YtDlpError
from app.media.ffmpeg import FfmpegRunner, FfmpegError
from app.security.url_validator import validate_youtube_url, UnsupportedURLError

logger = logging.getLogger(__name__)

# Output directory for completed downloads (inside repo staging/)
from app.media.process_control import suspend_process, resume_process
import subprocess

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DOWNLOADS_DIR = _REPO_ROOT / "staging" / "downloads"


class JobRunner:
    """
    Executes a single download job end-to-end.

    Instantiate once per job; call run() as an asyncio task.
    """

    def __init__(
        self,
        job: Job,
        store: JobStore,
        ytdlp: YtDlpRunner,
        ffmpeg: FfmpegRunner | None,
    ) -> None:
        self._job = job
        self._store = store
        self._ytdlp = ytdlp
        self._ffmpeg = ffmpeg
        self._proc: subprocess.Popen | None = None
        self._is_paused: bool = False

    def _set_proc(self, proc: subprocess.Popen) -> None:
        self._proc = proc

    def pause(self) -> bool:
        if self._proc and self._proc.poll() is None and not self._is_paused:
            if suspend_process(self._proc.pid):
                self._is_paused = True
                self._store.update(
                    self._job.job_id,
                    state="paused",
                    message="Download paused.",
                )
                return True
        return False

    def resume(self) -> bool:
        if self._proc and self._proc.poll() is None and self._is_paused:
            if resume_process(self._proc.pid):
                self._is_paused = False
                self._store.update(
                    self._job.job_id,
                    state="downloading",
                    message="Resuming download…",
                )
                return True
        return False

    def cancel(self) -> None:
        if self._proc and self._proc.poll() is None:
            if self._is_paused:
                resume_process(self._proc.pid)
            try:
                self._proc.terminate()
            except Exception:
                pass

    async def run(self) -> None:
        """Top-level coroutine. Catches all exceptions and marks the job terminal."""
        job = self._job
        try:
            await self._execute(job)
        except asyncio.CancelledError:
            self._store.update(
                job.job_id,
                state="cancelled",
                message="Cancelled by server.",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
        except UnsupportedURLError as exc:
            self._store.mark_failed(job.job_id, str(exc))
        except (YtDlpError, FfmpegError) as exc:
            logger.error("Job %s failed: %s", job.job_id, exc)
            self._store.mark_failed(job.job_id, str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error in job %s", job.job_id)
            self._store.mark_failed(job.job_id, f"Internal error: {exc}")

    async def _execute(self, job: Job) -> None:
        _DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

        # ── 1. Validate URL ───────────────────────────────────────────────────
        self._check_cancel(job)
        canonical_url = validate_youtube_url(job.url)

        # ── 2. Determine format type ──────────────────────────────────────────
        is_gif     = getattr(job, "is_gif", False)
        is_audio_only = job.format_id.startswith("bestaudio/")
        audio_ext = job.format_id.split("/")[1] if is_audio_only else None
        # Decode quality suffix: "bestaudio/mp3:320k" -> ext="mp3", quality="320k"
        audio_quality = "0"  # default VBR best
        if is_audio_only and audio_ext and ":" in audio_ext:
            audio_ext, audio_quality = audio_ext.split(":", 1)

        # Resolve title + channel if not provided at job creation
        if not job.title:
            try:
                meta = await self._ytdlp.fetch_metadata(canonical_url)
                if meta:
                    upd: dict = {}
                    if meta.title:
                        upd["title"] = meta.title
                    if meta.uploader and not getattr(job, "channel", None):
                        upd["channel"] = meta.uploader
                    if upd:
                        self._store.update(job.job_id, **upd)
            except Exception:
                pass

        # ── 3. Determine output directory (channel sub-folder if available) ───
        channel = getattr(job, "channel", None) or None
        if channel:
            safe_channel = _safe_dirname(channel)
            out_dir = _DOWNLOADS_DIR / safe_channel
        else:
            out_dir = _DOWNLOADS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        # ── 4. Download ───────────────────────────────────────────────────────
        self._store.update(
            job.job_id,
            state="downloading",
            progress_percent=0.0,
            message="Starting download…",
        )
        self._check_cancel(job)

        # Clip times from job — present for Timestamp/Clip mode
        start_time: str | None = getattr(job, "start_time", None) or None
        end_time: str | None   = getattr(job, "end_time", None)   or None

        # GIF: download as mp4 clip first, then convert
        dl_ext = "mp4" if is_gif else (f"{audio_ext}" if is_audio_only else f"{job.output_format or 'mp4'}")
        suffix = f".{dl_ext}"
        safe_id = hashlib.sha1(job.job_id.encode()).hexdigest()[:12]
        output_path = out_dir / f"{safe_id}{suffix}"

        format_spec = job.format_id
        if is_audio_only and audio_ext:
            gen = self._ytdlp.download_audio(
                canonical_url,
                audio_format=audio_ext,
                output_path=output_path,
                ffmpeg_exe=Path(self._ffmpeg._exe) if self._ffmpeg else None,
                on_proc=self._set_proc,
                audio_quality=audio_quality,
                start_time=start_time,
                end_time=end_time,
            )
        else:
            if "+" not in format_spec:
                format_spec = f"{format_spec}+bestaudio/best"

            # Build a graceful fallback chain so that if the specific format ID
            # has expired on YouTube's CDN, yt-dlp degrades to the best
            # available equivalent quality rather than hard-failing.
            height_fallback = _resolution_fallback(job.format_id)
            if height_fallback:
                format_spec = f"{format_spec}/{height_fallback}+bestaudio/best"
            else:
                format_spec = f"{format_spec}/bestvideo+bestaudio/best"

            gen = self._ytdlp.download(
                canonical_url,
                format_id=format_spec,
                output_path=output_path,
                ffmpeg_exe=Path(self._ffmpeg._exe) if self._ffmpeg else None,
                merge_output_format="mp4",
                on_proc=self._set_proc,
                start_time=start_time,
                end_time=end_time,
            )

        seen_second_stream = False
        last_raw_pct = 0.0
        async for pct in gen:
            self._check_cancel(job)
            if pct < last_raw_pct and last_raw_pct > 75.0:
                seen_second_stream = True
            last_raw_pct = pct

            if is_audio_only:
                scaled = round(pct * 0.80, 1)
                msg = f"Downloading audio… {pct:.0f}%"
            elif not seen_second_stream:
                scaled = round(pct * 0.65, 1)
                msg = f"Downloading video… {pct:.0f}%"
            else:
                scaled = round(65.0 + (pct * 0.13), 1)
                msg = f"Downloading audio… {pct:.0f}%"

            self._store.update(
                job.job_id,
                progress_percent=scaled,
                message=msg,
            )

        # ── 5. Merge step ────────────────────────────────────────────────────
        needs_merge = (
            not is_audio_only
            and ("+" in format_spec or "+" in job.format_id)
            and self._ffmpeg is not None
        )
        if needs_merge and self._ffmpeg is not None:
            self._check_cancel(job)
            self._store.update(
                job.job_id,
                state="merging",
                progress_percent=78.0,
                message="Merging audio and video streams…",
            )
        # ── 6. Validate downloaded file ───────────────────────────────────────
        self._check_cancel(job)
        actual_path = _find_output(output_path)
        if actual_path is None or not actual_path.exists() or actual_path.stat().st_size == 0:
            raise YtDlpError(
                "Output file not found or empty after download. "
                "Check that yt-dlp and FFmpeg are installed and active."
            )

        # ── 6b. Post-download trimming (Timestamp/Clip mode) ─────────────────
        if (start_time or end_time) and self._ffmpeg and not is_gif:
            self._check_cancel(job)
            self._store.update(
                job.job_id,
                state="merging",
                progress_percent=80.0,
                message="Clipping selected section…",
            )
            trimmed_path = actual_path.with_name(f"{actual_path.stem}_clipped{actual_path.suffix}")
            ok = await self._ffmpeg.trim_clip(
                input_path=actual_path,
                output_path=trimmed_path,
                start_time=start_time,
                end_time=end_time,
            )
            if ok and trimmed_path.exists() and trimmed_path.stat().st_size > 0:
                try:
                    actual_path.unlink(missing_ok=True)
                except Exception:
                    pass
                actual_path = trimmed_path
            else:
                logger.warning("Trimming failed for job %s; using full file", job.job_id)

        # ── 7. GIF conversion (two-pass palette) ─────────────────────────────
        if is_gif and self._ffmpeg:
            self._store.update(
                job.job_id,
                state="converting",
                progress_percent=82.0,
                message="Converting to GIF…",
            )
            gif_path = actual_path.with_suffix(".gif")
            ok = await self._ffmpeg.to_gif(
                input_path=actual_path,
                output_path=gif_path,
                fps=10,
                width=480,
                # GIF clips: the mp4 already has the section; no need to re-clip
            )
            if ok:
                try:
                    actual_path.unlink(missing_ok=True)  # remove temp mp4
                except Exception:
                    pass
                actual_path = gif_path
            else:
                logger.warning("GIF conversion failed for job %s; keeping mp4", job.job_id)

        # ── 8. ID3 / metadata embedding (audio only) ──────────────────────────
        if is_audio_only and self._ffmpeg and not is_gif:
            self._store.update(
                job.job_id,
                progress_percent=90.0,
                message="Embedding metadata…",
            )
            try:
                await _embed_metadata(
                    actual_path,
                    title=getattr(job, "title", None),
                    artist=getattr(job, "channel", None),
                    ffmpeg_exe=Path(self._ffmpeg._exe),
                )
            except Exception as exc:
                logger.warning("Metadata embedding failed for %s: %s", job.job_id, exc)

        # ── 9. Waveform generation (audio only, silent — never blocks completion) ──
        if is_audio_only and self._ffmpeg and not is_gif:
            try:
                waveform_path = actual_path.with_suffix(".wave.png")
                ok = await self._ffmpeg.waveform_png(
                    audio_path=actual_path,
                    output_path=waveform_path,
                    width=320,
                    height=64,
                    color="#7c3aed",
                )
                if ok:
                    self._store.update(job.job_id, waveform_path=str(waveform_path))
            except Exception as exc:
                logger.warning("Waveform generation failed for %s: %s", job.job_id, exc)

        # ── 10. Validate final output ─────────────────────────────────────────
        self._store.update(
            job.job_id,
            state="validating",
            progress_percent=98.0,
            message="Validating output file…",
        )
        if not actual_path.exists() or actual_path.stat().st_size == 0:
            raise YtDlpError(
                "Output file not found or empty after post-processing. "
                "Check that FFmpeg is installed and active."
            )

        logger.info("Job %s complete: %s (%.1f KB)", job.job_id, actual_path.name, actual_path.stat().st_size / 1024)

        # ── 11. Complete ──────────────────────────────────────────────────────
        self._store.mark_completed(job.job_id, output_path=str(actual_path))


    def _check_cancel(self, job: Job) -> None:
        if job.cancel_requested:
            self.cancel()
            raise asyncio.CancelledError


def _find_output(expected: Path) -> Path | None:
    """
    yt-dlp may write a slightly different extension (e.g. .webm→.mp4 after merge,
    or append container extensions on sections like .mp4.webm before remuxing).
    Find the most recently written completed media file matching the stem.
    """
    if expected.exists() and not expected.name.endswith(".part"):
        return expected
    stem = expected.stem
    parent = expected.parent
    # Check both direct stem and prefix matches, excluding .part, .tmp, and .wave.png
    candidates = [
        p for p in parent.glob(f"{stem}*")
        if p.is_file()
        and not p.name.endswith(".part")
        and not p.name.endswith(".tmp")
        and not p.name.endswith(".wave.png")
        and p.stat().st_size > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# Map well-known yt-dlp numeric format IDs to height-based fallback selectors.
# This allows the download to degrade gracefully when a specific format ID
# has expired on YouTube's CDN (which happens frequently for adaptive streams).
_FORMAT_HEIGHT_MAP: dict[str, int] = {
    "137": 1080, "299": 1080, "248": 1080, "303": 1080,
    "136": 720,  "298": 720,  "247": 720,  "302": 720,
    "135": 480,  "244": 480,
    "134": 360,  "243": 360,
    "133": 240,  "242": 240,
    "160": 144,  "278": 144,
    # 4K / 8K
    "315": 2160, "313": 2160, "272": 2160,
    "571": 4320,
}


def _resolution_fallback(format_id: str) -> str | None:
    """
    Given a format_id (possibly "137+251" or just "137"), return a yt-dlp
    bestvideo height selector to use as a fallback when the ID is unavailable.
    Returns None when the format_id cannot be mapped (e.g. non-numeric IDs).
    """
    # Strip audio stream suffix if present ("137+251" -> "137")
    vid_id = format_id.split("+")[0].strip()
    height = _FORMAT_HEIGHT_MAP.get(vid_id)
    if height:
        return f"bestvideo[height<={height}]"
    return None


import re as _re

def _safe_dirname(name: str) -> str:
    """
    Sanitize a channel/uploader name into a safe directory name that works
    on Windows, macOS, and Linux.  Keeps Unicode letters and numbers.
    """
    cleaned = _re.sub(r'[\x00-\x1f*?"<>|/\\:]+', "_", name)
    cleaned = cleaned.strip(". ")
    return cleaned[:80] or "unknown_channel"


async def _embed_metadata(
    path: Path,
    title: str | None,
    artist: str | None,
    ffmpeg_exe: Path,
) -> None:
    """
    Embed ID3-style metadata (title, artist) into an audio file using an
    FFmpeg copy-remux.  Supports MP3, M4A, FLAC, WAV (where applicable).
    The original file is replaced in-place.
    """
    import tempfile
    if not title and not artist:
        return  # nothing to embed

    with tempfile.NamedTemporaryFile(suffix=path.suffix, delete=False) as tf:
        tmp = Path(tf.name)
    meta_args: list[str] = []
    if title:
        meta_args += ["-metadata", f"title={title}"]
    if artist:
        meta_args += ["-metadata", f"artist={artist}"]
        meta_args += ["-metadata", f"album_artist={artist}"]

    cmd = [
        str(ffmpeg_exe), "-y",
        "-i", str(path),
        "-c", "copy",          # no re-encode — just remux
        *meta_args,
        str(tmp),
    ]
    proc = await asyncio.to_thread(
        lambda: subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    )
    if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(path)   # atomic replace
    else:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        logger.warning("_embed_metadata failed: %s", proc.stderr[:200])

