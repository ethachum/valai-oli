"""
Valaioli — yt-dlp subprocess wrapper (Stage 3).

All calls use an arg-array; no shell=True is ever used.
Binary path always comes from ManifestService — never hardcoded.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Progress-line regex ───────────────────────────────────────────────────────
# Matches:
#   "[download]  47.3% of 52.00MiB"
#   "[download] 100% of 4.56MiB"
#   "[valaioli-progress] 47.3%"
_PROGRESS_RE = re.compile(
    r"(?:\[download\]|\[valaioli-progress\])\s+(?P<pct>[\d.]+)%",
    re.IGNORECASE,
)


def _get_js_runtime_args() -> list[str]:
    """
    Detect available JS runtime (Node, Deno, Bun, QuickJS) for yt-dlp.
    YouTube requires solving signature and 'n' challenges using a JS runtime;
    without it, downloads throttle or fail with 'HTTP Error 403: Forbidden'.
    """
    node_path = shutil.which("node") or shutil.which("node.exe")
    if node_path:
        return ["--js-runtimes", f"node:{node_path}"]

    for runtime in ("deno", "bun", "quickjs"):
        p = shutil.which(runtime)
        if p:
            return ["--js-runtimes", f"{runtime}:{p}"]

    win_node = Path(r"C:\Program Files\nodejs\node.exe")
    if win_node.exists():
        return ["--js-runtimes", f"node:{win_node}"]
    return ["--js-runtimes", "node"]


_RETRY_ARGS: list[str] = [
    "--retries", "10",
    "--fragment-retries", "10",
    "--retry-sleep", "fragment:exp=1:20",
    "--file-access-retries", "5",
    "--extractor-retries", "5",
]


@dataclass
class FormatInfo:
    format_id: str
    ext: str
    resolution: str | None
    vcodec: str | None
    acodec: str | None
    filesize_approx: int | None
    has_video: bool
    has_audio: bool
    note: str | None


@dataclass
class VideoMetadata:
    title: str
    thumbnail: str | None
    duration_seconds: int | None
    uploader: str | None
    formats: list[FormatInfo] = field(default_factory=list)


@dataclass
class PlaylistEntry:
    """A single item stub from a flat-playlist extraction."""
    index: int                   # 1-based position in playlist
    video_id: str
    title: str
    thumbnail: str | None
    duration_seconds: int | None
    url: str                     # canonical watch URL


@dataclass
class PlaylistMetadata:
    playlist_id: str
    title: str
    uploader: str | None
    entry_count: int
    entries: list[PlaylistEntry] = field(default_factory=list)


class YtDlpError(RuntimeError):
    """Raised when yt-dlp exits non-zero or produces unexpected output."""


class YtDlpRunner:
    """Async interface to yt-dlp. Binary path injected from ManifestService."""

    def __init__(self, exe: Path) -> None:
        self._exe = exe

    # ── Metadata extraction ───────────────────────────────────────────────────

    async def fetch_metadata(self, url: str) -> VideoMetadata:
        """
        Run yt-dlp --dump-json to extract title, thumbnail, duration,
        uploader, and available formats. Network-bound; runs in asyncio subprocess.
        """
        cmd = [
            str(self._exe),
            "--dump-json",
            "--no-playlist",
            "--no-warnings",
            "--skip-download",
            *_get_js_runtime_args(),
            url,
        ]
        logger.debug("yt-dlp metadata cmd: %s", cmd)
        stdout, stderr = await _run_subprocess(cmd)
        if not stdout.strip():
            raise YtDlpError(f"yt-dlp produced no output. stderr: {stderr[:500]}")

        try:
            data: dict[str, Any] = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise YtDlpError(f"yt-dlp JSON parse error: {exc}") from exc

        return _parse_metadata(data)

    # ── Playlist metadata extraction ──────────────────────────────────────────

    async def fetch_playlist_metadata(self, url: str) -> "PlaylistMetadata":
        """
        Run yt-dlp --flat-playlist --dump-single-json to retrieve full playlist
        metadata including title and all entry stubs (id, title, thumbnail,
        duration) without fetching individual video pages.
        """
        cmd = [
            str(self._exe),
            "--flat-playlist",
            "--dump-single-json",
            "--no-warnings",
            *_get_js_runtime_args(),
            url,
        ]
        logger.debug("yt-dlp playlist metadata cmd: %s", cmd)
        stdout, stderr = await _run_subprocess(cmd)
        if not stdout.strip():
            raise YtDlpError(f"yt-dlp produced no playlist output. stderr: {stderr[:500]}")

        try:
            data: dict[str, Any] = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise YtDlpError(f"yt-dlp playlist JSON parse error: {exc}") from exc

        return _parse_playlist_metadata(data)

    async def download(
        self,
        url: str,
        format_id: str,
        output_path: Path,
        ffmpeg_exe: Path | None = None,
        merge_output_format: str | None = None,
        on_proc: Callable[[subprocess.Popen], None] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> AsyncGenerator[float, None]:
        """
        Stream a yt-dlp download to *output_path*.

        Yields progress floats (0.0–100.0) as yt-dlp emits them.
        The caller is responsible for catching YtDlpError.

        start_time / end_time: optional HH:MM:SS or seconds strings used with
        --download-sections to clip the output (requires ffmpeg).
        """
        cmd = [
            str(self._exe),
            "--no-playlist",
            "--no-warnings",
            "--newline",          # one progress line per line for easy parsing
            "--progress-template", "download:[valaioli-progress] %(progress._percent_str)s",
            "--concurrent-fragments", "3",
            "--buffer-size", "1024k",
            *_RETRY_ARGS,
            *_get_js_runtime_args(),
            "-f", format_id,
            "-o", str(output_path),
        ]
        if ffmpeg_exe:
            cmd += ["--ffmpeg-location", str(ffmpeg_exe.parent)]
            if merge_output_format:
                cmd += ["--merge-output-format", merge_output_format]
        cmd.append(url)

        logger.debug("yt-dlp download cmd: %s", cmd)
        async for line in _stream_subprocess(cmd, on_proc=on_proc):
            m = _PROGRESS_RE.search(line)
            if m:
                yield float(m.group("pct"))

        return  # generator sentinel

    async def download_audio(
        self,
        url: str,
        audio_format: str,        # "mp3", "m4a", "wav", "flac"
        output_path: Path,
        ffmpeg_exe: Path | None = None,
        on_proc: Callable[[subprocess.Popen], None] | None = None,
        audio_quality: str = "0",   # "0" = best; "320k" for CBR MP3
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> AsyncGenerator[float, None]:
        """
        Download and convert to a pure-audio format.
        Yields progress floats.

        audio_format: target codec container (mp3, m4a, wav, flac).
        audio_quality: yt-dlp --audio-quality value; "0" = VBR best,
                       "320k" = CBR 320 kbps (MP3 only).
        start_time / end_time: optional clip bounds (HH:MM:SS or seconds).
        """
        cmd = [
            str(self._exe),
            "--no-playlist",
            "--no-warnings",
            "--newline",
            "--progress-template", "download:[valaioli-progress] %(progress._percent_str)s",
            "--concurrent-fragments", "3",
            "--buffer-size", "1024k",
            *_RETRY_ARGS,
            *_get_js_runtime_args(),
            "-f", "bestaudio",
            "--extract-audio",
            "--audio-format", audio_format,
            "--audio-quality", audio_quality,
            "-o", str(output_path),
        ]
        if ffmpeg_exe:
            cmd += ["--ffmpeg-location", str(ffmpeg_exe.parent)]
        cmd.append(url)

        logger.debug("yt-dlp audio cmd: %s", cmd)
        async for line in _stream_subprocess(cmd, on_proc=on_proc):
            m = _PROGRESS_RE.search(line)
            if m:
                yield float(m.group("pct"))

        return


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _run_subprocess(cmd: list[str]) -> tuple[str, str]:
    """Run a subprocess to completion; return (stdout, stderr)."""
    def _execute():
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr

    returncode, stdout, stderr = await asyncio.to_thread(_execute)
    if returncode != 0:
        raise YtDlpError(
            f"yt-dlp exited {returncode}. stderr: {stderr[:1000]}"
        )
    return stdout, stderr


async def _stream_subprocess(
    cmd: list[str],
    on_proc: Callable[[subprocess.Popen], None] | None = None,
) -> AsyncGenerator[str, None]:
    """Start a subprocess and yield each stdout line as it arrives."""
    q: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    exit_holder: list[int] = []
    stderr_holder: list[str] = []

    def _worker():
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if on_proc:
            loop.call_soon_threadsafe(on_proc, proc)
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if line:
                loop.call_soon_threadsafe(q.put_nowait, line)
        proc.wait()
        exit_holder.append(proc.returncode)
        if proc.stderr:
            stderr_holder.append(proc.stderr.read())
        loop.call_soon_threadsafe(q.put_nowait, None)

    task = asyncio.create_task(asyncio.to_thread(_worker))
    try:
        while True:
            line = await q.get()
            if line is None:
                break
            logger.debug("[yt-dlp] %s", line)
            yield line
    finally:
        await task

    ret = exit_holder[0] if exit_holder else 0
    if ret not in (0, None):
        err = stderr_holder[0] if stderr_holder else ""
        raise YtDlpError(
            f"yt-dlp exited {ret}. stderr: {err[:500]}"
        )


# ── Metadata parser ───────────────────────────────────────────────────────────

# Formats with these vcodecs are audio-only
_AUDIO_ONLY_VCODECS = frozenset({"none", None, ""})

# Minimum formats to surface (avoids exposing 200+ raw yt-dlp formats)
_PREFERRED_HEIGHTS = (4320, 2160, 1440, 1080, 720, 480, 360)
_PREFERRED_AUDIO_EXTS = ("mp3", "m4a", "wav")


def _parse_metadata(data: dict[str, Any]) -> VideoMetadata:
    title: str = data.get("title") or "Unknown title"
    thumbnail: str | None = data.get("thumbnail")
    raw_duration = data.get("duration")
    duration: int | None = int(raw_duration) if raw_duration is not None else None
    uploader: str | None = data.get("uploader") or data.get("channel")

    raw_formats: list[dict] = data.get("formats") or []
    formats = _select_formats(raw_formats)

    return VideoMetadata(
        title=title,
        thumbnail=thumbnail,
        duration_seconds=duration,
        uploader=uploader,
        formats=formats,
    )


def _select_formats(raw: list[dict]) -> list[FormatInfo]:
    """
    Produce a curated, deduplicated list of download options.

    Video:  best progressive or adaptive stream for each preferred height (8K down to 360p).
    Audio:  bestaudio presented as mp3, m4a, wav conversion targets.
    """
    selected: list[FormatInfo] = []
    seen_heights: set[int] = set()

    # ── Video formats ─────────────────────────────────────────────────────────
    for raw_fmt in reversed(raw):  # yt-dlp orders ascending quality; reverse for best-first
        vcodec = (raw_fmt.get("vcodec") or "").lower()
        acodec = (raw_fmt.get("acodec") or "").lower()
        if vcodec in ("none", ""):
            continue  # audio-only stream

        height: int | None = raw_fmt.get("height")
        width: int | None = raw_fmt.get("width")
        if height is None and width is None:
            continue

        # Map to standard resolution tiers (supports 8K, 4K, 2K, etc. including non-16:9 ratios)
        eff_height = height or 0
        if eff_height >= 4320 or (width and width >= 7680):
            tier = 4320
        elif eff_height >= 2160 or (width and width >= 3840):
            tier = 2160
        elif eff_height >= 1440 or (width and width >= 2560):
            tier = 1440
        elif eff_height >= 1080 or (width and width >= 1920):
            tier = 1080
        elif eff_height >= 720 or (width and width >= 1280):
            tier = 720
        elif eff_height >= 480 or (width and width >= 854):
            tier = 480
        elif eff_height >= 360 or (width and width >= 640):
            tier = 360
        else:
            continue

        if tier in seen_heights:
            continue
        seen_heights.add(tier)

        ext = raw_fmt.get("ext") or "mp4"
        needs_merge = acodec in ("none", "")
        fps = raw_fmt.get("fps")
        fps_str = f" {int(fps)}fps" if fps and fps >= 50 else ""

        if tier == 4320:
            res_label = f"8K · 4320p{fps_str}"
        elif tier == 2160:
            res_label = f"4K · 2160p{fps_str}"
        elif tier == 1440:
            res_label = f"2K · 1440p{fps_str}"
        else:
            res_label = f"{tier}p{fps_str}"

        note_parts = [res_label]
        if needs_merge:
            note_parts.append("merge required")

        base_id = raw_fmt.get("format_id", "")
        format_id = f"{base_id}+bestaudio" if needs_merge and base_id else base_id

        selected.append(FormatInfo(
            format_id=format_id,
            ext=ext if ext != "webm" else "mp4",   # prefer mp4 container label
            resolution=f"{width or '?' }×{height or tier}",
            vcodec=raw_fmt.get("vcodec"),
            acodec=raw_fmt.get("acodec") if not needs_merge else "opus",
            filesize_approx=raw_fmt.get("filesize") or raw_fmt.get("filesize_approx"),
            has_video=True,
            has_audio=True,
            note=" · ".join(note_parts),
        ))

    # ── Audio-only formats ────────────────────────────────────────────────────
    for audio_ext in _PREFERRED_AUDIO_EXTS:
        # Estimate filesize from best audio stream
        best_audio = _best_audio_format(raw)
        fsize = (best_audio.get("filesize") or best_audio.get("filesize_approx")) if best_audio else None

        quality_notes = {"mp3": "192kbps", "m4a": "AAC 128kbps", "wav": "lossless PCM"}
        selected.append(FormatInfo(
            format_id=f"bestaudio/{audio_ext}",
            ext=audio_ext,
            resolution=None,
            vcodec=None,
            acodec={"mp3": "mp3", "m4a": "aac", "wav": "pcm_s16le"}[audio_ext],
            filesize_approx=fsize,
            has_video=False,
            has_audio=True,
            note=f"{audio_ext.upper()} · {quality_notes[audio_ext]}",
        ))

    return selected


def _best_audio_format(raw: list[dict]) -> dict | None:
    audio_only = [
        f for f in raw
        if (f.get("vcodec") or "none").lower() in ("none", "")
        and (f.get("acodec") or "none").lower() not in ("none", "")
    ]
    if not audio_only:
        return None
    return max(audio_only, key=lambda f: f.get("abr") or f.get("tbr") or 0)


def _parse_playlist_metadata(data: dict[str, Any]) -> PlaylistMetadata:
    """Parse flat-playlist dump from yt-dlp into PlaylistMetadata."""
    playlist_id = data.get("id") or ""
    title = data.get("title") or "Untitled Playlist"
    uploader = data.get("uploader") or data.get("channel") or None
    raw_entries = data.get("entries") or []

    entries: list[PlaylistEntry] = []
    idx = 1
    for item in raw_entries:
        if not item:
            continue
        vid_id = item.get("id") or ""
        item_title = item.get("title") or f"Video {idx}"
        duration = int(item["duration"]) if item.get("duration") is not None else None

        thumb = None
        if item.get("thumbnails"):
            thumb = item["thumbnails"][-1].get("url")
        elif item.get("thumbnail"):
            thumb = item.get("thumbnail")
        elif vid_id:
            thumb = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"

        watch_url = f"https://www.youtube.com/watch?v={vid_id}" if vid_id else ""

        entries.append(PlaylistEntry(
            index=idx,
            video_id=vid_id,
            title=item_title,
            thumbnail=thumb,
            duration_seconds=duration,
            url=watch_url,
        ))
        idx += 1

    return PlaylistMetadata(
        playlist_id=playlist_id,
        title=title,
        uploader=uploader,
        entry_count=len(entries),
        entries=entries,
    )

