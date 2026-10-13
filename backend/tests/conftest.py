"""
Valaioli — shared pytest fixtures (Stage 5).

This conftest provides:
  - A ``no_tools_app`` TestClient whose manifest reports NO active tool versions.
  - A ``tools_app`` TestClient whose manifest reports yt-dlp as active (uses real manifest).
  - Helpers that patch FastAPI's DI layer so individual tests can choose their isolation level.

All fixtures that touch app.state are designed to be independent of what is
actually installed on the host machine.
"""
from __future__ import annotations

import json
import pytest

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.manifest import ManifestService
from app.jobs import JobService
from app.api._deps import get_manifest_service, get_job_service


# ─────────────────────────────────────────────────────────────────────────────
# Manifest factories
# ─────────────────────────────────────────────────────────────────────────────

def _build_empty_manifest(tmp_path) -> ManifestService:
    """Return a ManifestService whose manifest has NO active tool versions."""
    data = {
        "schemaVersion": 1,
        "ytDlp": {
            "activeVersion": None,
            "lastCheckUtc": None,
            "lastOutcome": "not-checked",
        },
        "ffmpeg": {
            "activeVersion": None,
            "lastCheckUtc": None,
            "lastOutcome": "not-checked",
        },
    }
    p = tmp_path / "media-tools.lock.json"
    p.write_text(json.dumps(data))
    return ManifestService(p)


def _build_candidate_manifest(tmp_path) -> ManifestService:
    """Return a ManifestService with yt-dlp active and an FFmpeg update candidate."""
    data = {
        "schemaVersion": 1,
        "ytDlp": {
            "activeVersion": "2026.08.19",
            "lastCheckUtc": "2026-09-01T00:00:00Z",
            "lastOutcome": "up-to-date",
        },
        "ffmpeg": {
            "activeVersion": None,
            "lastCheckUtc": "2026-09-01T00:00:00Z",
            "lastOutcome": "update-available",
            "candidate": {
                "version": "9.0.2",
                "status": "pending",
                "releaseUrl": "https://github.com/BtbN/FFmpeg-Builds/releases",
                "checkedAtUtc": "2026-09-01T00:00:00Z",
            },
        },
    }
    p = tmp_path / "media-tools.lock.json"
    p.write_text(json.dumps(data))
    return ManifestService(p)


# ─────────────────────────────────────────────────────────────────────────────
# App clients
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def no_tools_client(tmp_path):
    """
    TestClient where the manifest has NO active tool versions.
    Safe for tests that expect 503 / tools-not-installed behaviour.
    """
    manifest = _build_empty_manifest(tmp_path)
    application = create_app()

    # Override DI using FastAPI's dependency_overrides
    job_svc = JobService(manifest)
    application.dependency_overrides[get_manifest_service] = lambda: manifest
    application.dependency_overrides[get_job_service] = lambda: job_svc

    with TestClient(application) as c:
        yield c
        application.dependency_overrides.clear()


@pytest.fixture()
def candidate_client(tmp_path):
    """
    TestClient whose manifest has yt-dlp active + an FFmpeg update candidate.
    Used for updater-status tests.
    """
    manifest = _build_candidate_manifest(tmp_path)
    application = create_app()

    job_svc = JobService(manifest)
    application.dependency_overrides[get_manifest_service] = lambda: manifest
    application.dependency_overrides[get_job_service] = lambda: job_svc

    with TestClient(application) as c:
        yield c
        application.dependency_overrides.clear()


@pytest.fixture()
def client():
    """
    Default TestClient — uses the real app and real manifest (whatever is installed).
    Tests using this fixture must tolerate tools being present or absent.
    """
    from app.main import app
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# Low-level unit fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def empty_manifest_svc(tmp_path):
    return _build_empty_manifest(tmp_path)


@pytest.fixture()
def candidate_manifest_svc(tmp_path):
    return _build_candidate_manifest(tmp_path)
