"""
Valaioli — Stage 3 + Stage 5 backend test suite.

Tests cover:
  - All existing API endpoints (health, tools, metadata stub, jobs CRUD)
  - URL validator (valid + invalid cases)
  - JobStore (create, get, update, cancel, complete, fail, evict)
  - YtDlpRunner metadata parser (_parse_metadata and _select_formats)
  - JobService tool-not-ready path (no manifest / no binary)
  - API error responses (503 when tools missing, 422 bad URL, 404 job)

Run with:
    cd backend
    .venv\\Scripts\\python.exe -m pytest tests/ -v

Note: Tests that assert "no tools installed" behaviour use the ``no_tools_client``
fixture (defined in conftest.py) so they are isolated from whatever is actually
installed on the host machine.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.jobs.store import JobStore
from app.jobs import JobService
from app.services.manifest import ManifestService
from app.security.url_validator import validate_youtube_url, UnsupportedURLError
from app.media.ytdlp import _parse_metadata, _select_formats


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def store():
    return JobStore()


@pytest.fixture()
def tmp_manifest(tmp_path):
    """Write a minimal manifest with no active versions and return its path."""
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
    return p


@pytest.fixture()
def manifest_svc(tmp_manifest):
    return ManifestService(tmp_manifest)


@pytest.fixture()
def job_svc(manifest_svc):
    return JobService(manifest_svc)


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Tools endpoint — reads real manifest (no active versions)
# ─────────────────────────────────────────────────────────────────────────────

def test_tools_returns_list(client):
    resp = client.get("/api/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    names = {t["name"] for t in data["tools"]}
    assert "yt-dlp" in names
    assert "ffmpeg" in names


def test_tools_versions_are_null_when_not_installed(no_tools_client):
    """Manifest has no active versions → both versions should be null."""
    resp = no_tools_client.get("/api/tools")
    for tool in resp.json()["tools"]:
        assert tool["active_version"] is None


# ─────────────────────────────────────────────────────────────────────────────
# URL Validator
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected_id", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ",     "dQw4w9WgXcQ"),
    ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ",     "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ",                "dQw4w9WgXcQ"),
    # Extra params must be stripped
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42",       "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxx", "dQw4w9WgXcQ"),
    ("https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=RDAMVMdQw4w9WgXcQ", "dQw4w9WgXcQ"),
])
def test_valid_youtube_urls(url, expected_id):
    canonical = validate_youtube_url(url)
    assert f"v={expected_id}" in canonical
    assert canonical.startswith("https://www.youtube.com/watch")


@pytest.mark.parametrize("url", [
    "http://malicious.com/watch?v=dQw4w9WgXcQ",
    "https://evil.com/?v=dQw4w9WgXcQ",
    "https://www.youtube.com/playlist?list=PLxxx",
    "https://www.youtube.com/channel/UC123",
    "not-a-url",
    "https://www.youtube.com/watch",
    "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=SHORT",
])
def test_invalid_youtube_urls(url):
    with pytest.raises(UnsupportedURLError):
        validate_youtube_url(url)


# ─────────────────────────────────────────────────────────────────────────────
# JobStore
# ─────────────────────────────────────────────────────────────────────────────

def test_store_create_and_get(store):
    job = store.create(url="https://www.youtube.com/watch?v=abc12345678", format_id="22")
    assert job.state == "queued"
    fetched = store.get(job.job_id)
    assert fetched is not None
    assert fetched.job_id == job.job_id


def test_store_get_missing(store):
    assert store.get("nonexistent-id") is None


def test_store_update_state(store):
    job = store.create(url="https://www.youtube.com/watch?v=abc12345678", format_id="22")
    store.update(job.job_id, state="downloading", progress_percent=25.0, message="Downloading…")
    updated = store.get(job.job_id)
    assert updated.state == "downloading"
    assert updated.progress_percent == 25.0


def test_store_mark_completed(store):
    job = store.create(url="https://www.youtube.com/watch?v=abc12345678", format_id="22")
    store.mark_completed(job.job_id)
    assert store.get(job.job_id).state == "completed"


def test_store_mark_failed(store):
    job = store.create(url="https://www.youtube.com/watch?v=abc12345678", format_id="22")
    store.mark_failed(job.job_id, "yt-dlp error: network timeout")
    j = store.get(job.job_id)
    assert j.state == "failed"
    assert "network timeout" in j.error


def test_store_request_cancel_queued(store):
    """Cancelling a queued job should transition it to cancelled immediately."""
    job = store.create(url="https://www.youtube.com/watch?v=abc12345678", format_id="22")
    store.request_cancel(job.job_id)
    assert store.get(job.job_id).state == "cancelled"


def test_store_evict_old(store):
    ids = []
    for i in range(5):
        job = store.create(url=f"https://www.youtube.com/watch?v={i:011d}", format_id="22")
        store.mark_completed(job.job_id)
        ids.append(job.job_id)
    store.evict_old(max_completed=3)
    remaining = [j for j in store.list_all() if j.state == "completed"]
    assert len(remaining) == 3


def test_store_to_dict(store):
    job = store.create(url="https://www.youtube.com/watch?v=abc12345678", format_id="22")
    d = job.to_dict()
    assert "job_id" in d
    assert d["state"] == "queued"
    assert d["error"] is None


# ─────────────────────────────────────────────────────────────────────────────
# yt-dlp metadata parser (unit tests — no subprocess)
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_YTDLP_OUTPUT = {
    "title": "Test Video",
    "thumbnail": "https://example.com/thumb.jpg",
    "duration": 300,
    "uploader": "Test Channel",
    "formats": [
        # 1080p adaptive video-only
        {
            "format_id": "137",
            "ext": "mp4",
            "height": 1080,
            "width": 1920,
            "vcodec": "avc1.640028",
            "acodec": "none",
            "filesize": 80_000_000,
        },
        # 720p adaptive video-only
        {
            "format_id": "136",
            "ext": "mp4",
            "height": 720,
            "width": 1280,
            "vcodec": "avc1.4d401f",
            "acodec": "none",
            "filesize": 45_000_000,
        },
        # 480p adaptive video-only
        {
            "format_id": "135",
            "ext": "mp4",
            "height": 480,
            "width": 854,
            "vcodec": "avc1.4d401e",
            "acodec": "none",
            "filesize": 20_000_000,
        },
        # Audio-only
        {
            "format_id": "251",
            "ext": "webm",
            "height": None,
            "vcodec": "none",
            "acodec": "opus",
            "abr": 160,
            "filesize": 5_000_000,
        },
    ],
}


def test_parse_metadata_title():
    meta = _parse_metadata(SAMPLE_YTDLP_OUTPUT)
    assert meta.title == "Test Video"
    assert meta.uploader == "Test Channel"
    assert meta.duration_seconds == 300


def test_parse_metadata_formats_contain_video():
    meta = _parse_metadata(SAMPLE_YTDLP_OUTPUT)
    video_fmts = [f for f in meta.formats if f.has_video]
    assert len(video_fmts) >= 2  # at least 1080p and 720p


def test_parse_metadata_formats_contain_audio():
    meta = _parse_metadata(SAMPLE_YTDLP_OUTPUT)
    audio_fmts = [f for f in meta.formats if not f.has_video]
    assert len(audio_fmts) >= 1   # at least one audio-only format


def test_parse_metadata_no_formats():
    data = {**SAMPLE_YTDLP_OUTPUT, "formats": []}
    meta = _parse_metadata(data)
    # Should still return audio targets (mp3, m4a, wav) with null filesize
    audio_only = [f for f in meta.formats if not f.has_video]
    assert len(audio_only) == 3   # mp3, m4a, wav always offered


def test_select_formats_deduplicates_heights():
    """Two 1080p formats should produce only one 1080p entry."""
    raw = [
        {"format_id": "137", "ext": "mp4", "height": 1080, "width": 1920, "vcodec": "avc1", "acodec": "none"},
        {"format_id": "248", "ext": "webm", "height": 1080, "width": 1920, "vcodec": "vp09", "acodec": "none"},
        {"format_id": "251", "ext": "webm", "height": None, "vcodec": "none", "acodec": "opus", "abr": 160},
    ]
    fmts = _select_formats(raw)
    p1080 = [f for f in fmts if f.has_video and f.resolution and "1080" in f.resolution]
    assert len(p1080) == 1


# ─────────────────────────────────────────────────────────────────────────────
# API — Jobs (real JobService, no tools installed)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_job_returns_202(client):
    resp = client.post("/api/jobs", json={
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "format_id": "22",
    })
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    # With no tools installed the runner fails immediately → state is failed or queued
    assert data["state"] in ("queued", "failed")


def test_get_job_not_found(client):
    resp = client.get("/api/jobs/nonexistent-id")
    assert resp.status_code == 404


def test_cancel_queued_job(no_tools_client):
    """Without tools the job fails immediately, so cancel returns failed/cancelled."""
    create = no_tools_client.post("/api/jobs", json={
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "format_id": "22",
    })
    job_id = create.json()["job_id"]
    cancel = no_tools_client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["state"] in ("cancelled", "failed")


def test_cancel_nonexistent_job(client):
    resp = client.post("/api/jobs/does-not-exist/cancel")
    assert resp.status_code == 404


def test_pause_nonexistent_job(client):
    resp = client.post("/api/jobs/does-not-exist/pause")
    assert resp.status_code == 404


def test_resume_nonexistent_job(client):
    resp = client.post("/api/jobs/does-not-exist/resume")
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# API — Metadata endpoint (no tools → 503)
# ─────────────────────────────────────────────────────────────────────────────

def test_metadata_503_when_tools_not_installed(no_tools_client):
    """With no active yt-dlp version in the manifest, /api/metadata returns 503."""
    resp = no_tools_client.post("/api/metadata", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert resp.status_code == 503
    assert "not installed" in resp.json()["detail"].lower()


def test_metadata_422_for_invalid_url(client):
    """Even with tools missing, a clearly invalid URL should be caught early."""
    resp = client.post("/api/metadata", json={"url": "not-a-youtube-url"})
    # Either 503 (tools checked first) or 422 (URL checked first)
    assert resp.status_code in (422, 503)


# ─────────────────────────────────────────────────────────────────────────────
# JobService — unit tests (no subprocess calls)
# ─────────────────────────────────────────────────────────────────────────────

def test_job_service_create_fails_without_tools(job_svc):
    """JobService with no installed tools should mark job failed immediately."""
    import asyncio
    # create_job is sync; the asyncio task runs in the background but we can
    # check that tools-not-ready path sets state to failed without waiting
    job = job_svc.create_job(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        format_id="22",
    )
    # State is either queued (task not yet run) or failed (already ran)
    assert job.state in ("queued", "failed")
    retrieved = job_svc.get_job(job.job_id)
    assert retrieved is not None


def test_job_service_cancel_nonexistent(job_svc):
    result = job_svc.cancel_job("nonexistent-id")
    assert result is None


def test_manifest_service_no_file(tmp_path):
    """ManifestService.get_ytdlp_path() raises FileNotFoundError if manifest absent."""
    svc = ManifestService(tmp_path / "nonexistent.json")
    with pytest.raises(FileNotFoundError):
        svc.get_ytdlp_path()


def test_manifest_service_reads_versions(tmp_manifest):
    svc = ManifestService(tmp_manifest)
    versions = svc.get_versions()
    assert "ytDlp" in versions
    assert "ffmpeg" in versions
    assert versions["ytDlp"]["activeVersion"] is None


def test_sanitize_filename():
    from app.api.jobs import sanitize_filename
    assert sanitize_filename("Rick Astley - Never Gonna Give You Up (Official)") == "Rick Astley - Never Gonna Give You Up (Official)"
    assert sanitize_filename('AC/DC: "Back in Black" *Live* <2020>?') == "AC - DC - Back in Black Live 2020"
    assert sanitize_filename("வாலாட்டி - பாடல் | Vaalatti Song") == "வாலாட்டி - பாடல் Vaalatti Song"
    assert sanitize_filename("   ...song...   ") == "song"
    assert sanitize_filename("CON") == "CON_media"
    assert sanitize_filename("") == "download"


def test_download_endpoint_uses_video_title(client, tmp_path):
    svc = client.app.state.job_service
    test_file = tmp_path / "song.mp3"
    test_file.write_bytes(b"dummy mp3 data")

    job = svc._store.create(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        format_id="bestaudio/mp3",
        output_format="mp3",
        title="Rick Astley - Never Gonna Give You Up",
    )
    svc._store.mark_completed(job.job_id, output_path=str(test_file))

    resp = client.get(f"/api/jobs/{job.job_id}/download")
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert "Rick%20Astley%20-%20Never%20Gonna%20Give%20You%20Up.mp3" in cd or "Rick Astley - Never Gonna Give You Up.mp3" in cd
    assert resp.content == b"dummy mp3 data"

    # Also test path-based download route
    resp_path = client.get(f"/api/jobs/{job.job_id}/download/Custom%20Song.mp3")
    assert resp_path.status_code == 200
    cd_path = resp_path.headers.get("content-disposition", "")
    assert "Custom Song.mp3" in cd_path or "Custom%20Song.mp3" in cd_path


def test_select_formats_includes_8k():
    raw = [
        {"format_id": "571", "ext": "mp4", "height": 4320, "width": 7680, "vcodec": "av01.0.12M.08", "acodec": "none", "fps": 60},
        {"format_id": "313", "ext": "webm", "height": 2160, "width": 3840, "vcodec": "vp09", "acodec": "none", "fps": 30},
        {"format_id": "137", "ext": "mp4", "height": 1080, "width": 1920, "vcodec": "avc1", "acodec": "none"},
        {"format_id": "251", "ext": "webm", "height": None, "vcodec": "none", "acodec": "opus", "abr": 160},
    ]
    fmts = _select_formats(raw)
    p8k = [f for f in fmts if f.has_video and f.resolution and "4320" in f.resolution]
    assert len(p8k) == 1
    assert p8k[0].note is not None
    assert "8K" in p8k[0].note
    assert "60fps" in p8k[0].note
    assert p8k[0].format_id == "571+bestaudio"


# ─────────────────────────────────────────────────────────────────────────────
# Playlist endpoints & URL validation
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_playlist_url():
    from app.security.url_validator import validate_playlist_url, is_playlist_url, UnsupportedURLError

    url = "https://www.youtube.com/playlist?list=PL1234567890abcdef"
    canonical, pl_id = validate_playlist_url(url)
    assert pl_id == "PL1234567890abcdef"
    assert canonical == "https://www.youtube.com/playlist?list=PL1234567890abcdef"
    assert is_playlist_url(url) is True

    # Watch URL with list param
    watch_pl = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890abcdef"
    canonical, pl_id = validate_playlist_url(watch_pl)
    assert pl_id == "PL1234567890abcdef"
    assert is_playlist_url(watch_pl) is True

    # YouTube Music playlist URL
    music_pl = "https://music.youtube.com/playlist?list=PL1234567890abcdef"
    canonical_m, pl_id_m = validate_playlist_url(music_pl)
    assert pl_id_m == "PL1234567890abcdef"
    assert canonical_m == "https://www.youtube.com/playlist?list=PL1234567890abcdef"
    assert is_playlist_url(music_pl) is True

    # YouTube Music album playlist
    album_pl = "https://music.youtube.com/playlist?list=OLAK5uy_kXgJ-6b83fT44abcdef"
    canonical_a, pl_id_a = validate_playlist_url(album_pl)
    assert pl_id_a == "OLAK5uy_kXgJ-6b83fT44abcdef"
    assert is_playlist_url(album_pl) is True

    # Non-playlist URL
    assert is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False

    with pytest.raises(UnsupportedURLError):
        validate_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_playlist_metadata_503_when_no_tools(no_tools_client):
    resp = no_tools_client.post(
        "/api/playlist/metadata",
        json={"url": "https://www.youtube.com/playlist?list=PL1234567890abcdef"},
    )
    assert resp.status_code == 503
    assert "yt-dlp is not installed" in resp.json()["detail"]


def test_create_playlist_jobs(client):
    payload = {
        "items": [
            {"index": 1, "title": "Track One", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "thumbnail": "https://example.com/1.jpg"},
            {"index": 2, "title": "Track Two", "url": "https://www.youtube.com/watch?v=oHg5SJYRHA0", "thumbnail": "https://example.com/2.jpg"},
        ],
        "preset": "1080p",
    }
    resp = client.post("/api/playlist/jobs", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert data["enqueued_count"] == 2
    assert len(data["job_ids"]) == 2

    # Check that jobs were created with numbered titles
    job_resp = client.get(f"/api/jobs/{data['job_ids'][0]}")
    assert job_resp.status_code == 200
    assert job_resp.json()["title"] == "01 - Track One"


