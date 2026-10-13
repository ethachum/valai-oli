"""
Valaioli — FFmpeg subprocess wrapper (Stage 3).

Used for stream merging (video+audio) and audio format conversion.
Binary path injected from ManifestService — never hardcoded.
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path

logger = logging.getLogger(__name__)

# FFmpeg progress lines look like:
# frame=  123 fps= 30 q=28.0 size=    1024kB time=00:00:04.10 bitrate=2048.0kbits/s speed=1.00x
_TIME_RE = re.compile(r"time=(\d+):(\d+):([\d.]+)", re.IGNORECASE)


class FfmpegError(RuntimeError):
    """Raised when ffmpeg exits non-zero."""


class FfmpegRunner:
    """Async interface to ffmpeg. Binary path injected at construction."""

    def __init__(self, exe: Path) -> None:
        self._exe = exe

    async def merge_streams(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        duration_seconds: float | None = None,
    ) -> AsyncGenerator[float, None]:
        """
        Merge separate video and audio streams into a single MP4.
        Yields progress floats (0–100) based on elapsed time vs. total duration.
        """
        cmd = [
            str(self._exe),
            "-y",                          # overwrite without asking
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",                # no re-encode — just remux
            "-c:a", "copy",
            "-movflags", "+faststart",     # moov atom at start for streaming
            str(output_path),
        ]
        logger.debug("ffmpeg merge cmd: %s", cmd)
        async for pct in _stream_ffmpeg(cmd, duration_seconds):
            yield pct

    async def convert_audio(
        self,
        input_path: Path,
        output_path: Path,
        codec: str = "libmp3lame",
        bitrate: str = "192k",
        duration_seconds: float | None = None,
    ) -> AsyncGenerator[float, None]:
        """
        Convert audio to a target codec/format.
        Yields progress floats (0–100).
        """
        cmd = [
            str(self._exe),
            "-y",
            "-i", str(input_path),
            "-vn",                  # strip video
            "-c:a", codec,
            "-b:a", bitrate,
            str(output_path),
        ]
        logger.debug("ffmpeg convert cmd: %s", cmd)
        async for pct in _stream_ffmpeg(cmd, duration_seconds):
            yield pct

    async def probe_duration(self, path: Path) -> float | None:
        """
        Use ffprobe to return the duration of a media file in seconds.
        Returns None if ffprobe is unavailable or the file has no duration.
        """
        ffprobe = self._exe.parent / ("ffprobe.exe" if self._exe.suffix == ".exe" else "ffprobe")
        if not ffprobe.exists():
            return None
        cmd = [
            str(ffprobe),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            def _probe():
                return subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

            proc = await asyncio.to_thread(_probe)
            return float(proc.stdout.strip())
        except Exception:
            return None

    async def waveform_png(
        self,
        audio_path: Path,
        output_path: Path,
        width: int = 320,
        height: int = 64,
        color: str = "#7c3aed",
    ) -> bool:
        """
        Generate a waveform PNG from an audio/video file using the
        showwavespic filter. Returns True on success, False on failure.
        The PNG is suitable for embedding as a visual preview in the UI.
        """
        color_hex = color.lstrip("#")
        cmd = [
            str(self._exe),
            "-y",
            "-i", str(audio_path),
            "-filter_complex",
            (
                f"aformat=channel_layouts=mono,"
                f"showwavespic=s={width}x{height}:colors=#{color_hex}"
            ),
            "-frames:v", "1",
            str(output_path),
        ]
        logger.debug("ffmpeg waveform cmd: %s", cmd)
        try:
            def _run():
                return subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            proc = await asyncio.to_thread(_run)
            if proc.returncode != 0:
                logger.warning("waveform generation failed: %s", proc.stderr[:300])
                return False
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as exc:
            logger.warning("waveform_png exception: %s", exc)
            return False

    async def trim_clip(
        self,
        input_path: Path,
        output_path: Path,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> bool:
        """
        Trim/clip a media file quickly using stream copying.
        Falls back to accurate re-encoding if stream copy fails.
        """
        seek_args: list[str] = []
        if start_time:
            seek_args += ["-ss", start_time]
        if end_time:
            seek_args += ["-to", end_time]

        cmd = [
            str(self._exe),
            "-y",
            *seek_args,
            "-i", str(input_path),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(output_path),
        ]
        logger.debug("ffmpeg trim cmd: %s", cmd)

        def _run(c: list[str]) -> int:
            proc = subprocess.run(
                c,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return proc.returncode

        ret = await asyncio.to_thread(_run, cmd)
        if ret == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return True

        # Fallback to keyframe-accurate re-encode if stream copy fails
        fallback_cmd = [
            str(self._exe),
            "-y",
            *seek_args,
            "-i", str(input_path),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            str(output_path),
        ]
        ret2 = await asyncio.to_thread(_run, fallback_cmd)
        return ret2 == 0 and output_path.exists() and output_path.stat().st_size > 0

    async def to_gif(
        self,
        input_path: Path,
        output_path: Path,
        fps: int = 10,
        width: int = 480,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> bool:
        """
        Convert a video clip to an optimised GIF using a two-pass palette
        approach (palettegen → paletteuse) for far better quality than a
        naive conversion.  Returns True on success.

        start_time / end_time: optional HH:MM:SS or seconds clip bounds
        applied to the *already downloaded* input file (not a live URL).
        """
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            palette_file = Path(tf.name)
        scale_filter = f"fps={fps},scale={width}:-1:flags=lanczos"

        # Timing args (seek on input so it's fast)
        seek_args: list[str] = []
        dur_args: list[str] = []
        if start_time:
            seek_args = ["-ss", start_time]
        if end_time and start_time:
            try:
                from datetime import timedelta
                def _to_secs(ts: str) -> float:
                    parts = ts.split(":")
                    parts = [float(p) for p in parts]
                    if len(parts) == 3:
                        return parts[0]*3600 + parts[1]*60 + parts[2]
                    if len(parts) == 2:
                        return parts[0]*60 + parts[1]
                    return parts[0]
                dur = _to_secs(end_time) - _to_secs(start_time)
                dur_args = ["-t", str(max(1, dur))]
            except Exception:
                pass
        elif end_time:
            dur_args = ["-to", end_time]

        try:
            # Pass 1 — generate palette
            p1_cmd = [
                str(self._exe), "-y",
                *seek_args, *dur_args,
                "-i", str(input_path),
                "-vf", f"{scale_filter},palettegen=max_colors=256:stats_mode=diff",
                str(palette_file),
            ]
            logger.debug("ffmpeg gif palette cmd: %s", p1_cmd)

            def _run1():
                return subprocess.run(
                    p1_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace",
                )
            p1 = await asyncio.to_thread(_run1)
            if p1.returncode != 0:
                logger.warning("GIF palette pass failed: %s", p1.stderr[:300])
                return False

            # Pass 2 — encode GIF using palette
            p2_cmd = [
                str(self._exe), "-y",
                *seek_args, *dur_args,
                "-i", str(input_path),
                "-i", str(palette_file),
                "-filter_complex",
                f"[0:v]{scale_filter}[v];[v][1:v]paletteuse=dither=bayer:bayer_scale=5",
                str(output_path),
            ]
            logger.debug("ffmpeg gif encode cmd: %s", p2_cmd)

            def _run2():
                return subprocess.run(
                    p2_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace",
                )
            p2 = await asyncio.to_thread(_run2)
            ok = p2.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
            if not ok:
                logger.warning("GIF encode pass failed: %s", p2.stderr[:300])
            return ok
        except Exception as exc:
            logger.warning("to_gif exception: %s", exc)
            return False
        finally:
            try:
                palette_file.unlink(missing_ok=True)
            except Exception:
                pass



# ── Internal helpers ──────────────────────────────────────────────────────────

async def _stream_ffmpeg(
    cmd: list[str],
    duration_seconds: float | None,
) -> AsyncGenerator[float, None]:
    """Run ffmpeg, yield progress 0–100 from stderr time= markers."""
    q: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    exit_holder: list[int] = []

    def _worker():
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stderr is not None
        for raw_line in proc.stderr:
            line = raw_line.rstrip()
            if line:
                loop.call_soon_threadsafe(q.put_nowait, line)
        proc.wait()
        exit_holder.append(proc.returncode)
        loop.call_soon_threadsafe(q.put_nowait, None)

    task = asyncio.create_task(asyncio.to_thread(_worker))
    try:
        while True:
            line = await q.get()
            if line is None:
                break
            logger.debug("[ffmpeg] %s", line)
            if duration_seconds:
                m = _TIME_RE.search(line)
                if m:
                    h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                    elapsed = h * 3600 + mn * 60 + s
                    pct = min(99.0, elapsed / duration_seconds * 100)
                    yield pct
    finally:
        await task

    ret = exit_holder[0] if exit_holder else 0
    if ret not in (0, None):
        raise FfmpegError(f"ffmpeg exited {ret}")

    yield 100.0
