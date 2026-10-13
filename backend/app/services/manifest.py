"""
Valaioli — ManifestService

Reads config/media-tools.lock.json and resolves active tool executable paths.
The backend must NEVER hardcode binary paths — always use this service.

Stage 3: full implementation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Resolve the manifest relative to the repository root.
# This file lives at: backend/app/services/manifest.py
# Repository root is four levels up: backend/app/services/ -> backend/app/ -> backend/ -> valaioli-app/
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = _REPO_ROOT / "config" / "media-tools.lock.json"


class ManifestService:
    """Read-only interface to media-tools.lock.json."""

    def __init__(self, manifest_path: Path = _MANIFEST_PATH) -> None:
        self._path = manifest_path

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            raise FileNotFoundError(
                f"Manifest not found at {self._path}. "
                "Run scripts/dependency-updater/install-candidate.ps1 to install tools."
            )
        with self._path.open(encoding="utf-8") as f:
            return json.load(f)

    # ── Public interface ──────────────────────────────────────────────────────

    def get_ytdlp_path(self) -> Path | None:
        """Return the absolute path to the active yt-dlp.exe, or None if unset."""
        data = self._load()
        version: str | None = data.get("ytDlp", {}).get("activeVersion")
        if not version:
            return None
        candidate = (
            _REPO_ROOT / "tools" / "versions" / "yt-dlp" / version / "yt-dlp.exe"
        )
        return candidate if candidate.exists() else None

    def get_ffmpeg_path(self) -> Path | None:
        """Return the absolute path to the active ffmpeg.exe, or None if unset."""
        data = self._load()
        version: str | None = data.get("ffmpeg", {}).get("activeVersion")
        if not version:
            return None
        candidate = (
            _REPO_ROOT / "tools" / "versions" / "ffmpeg" / version / "bin" / "ffmpeg.exe"
        )
        return candidate if candidate.exists() else None

    def get_ffprobe_path(self) -> Path | None:
        """Return the absolute path to the active ffprobe.exe, or None if unset."""
        data = self._load()
        version: str | None = data.get("ffmpeg", {}).get("activeVersion")
        if not version:
            return None
        candidate = (
            _REPO_ROOT / "tools" / "versions" / "ffmpeg" / version / "bin" / "ffprobe.exe"
        )
        return candidate if candidate.exists() else None

    def get_versions(self) -> dict[str, dict]:
        """Return a summary of active versions and last-check outcomes."""
        data = self._load()
        return {
            "ytDlp": {
                "activeVersion": data.get("ytDlp", {}).get("activeVersion"),
                "lastCheckUtc": data.get("ytDlp", {}).get("lastCheckUtc"),
                "lastOutcome": data.get("ytDlp", {}).get("lastOutcome"),
            },
            "ffmpeg": {
                "activeVersion": data.get("ffmpeg", {}).get("activeVersion"),
                "lastCheckUtc": data.get("ffmpeg", {}).get("lastCheckUtc"),
                "lastOutcome": data.get("ffmpeg", {}).get("lastOutcome"),
            },
        }
