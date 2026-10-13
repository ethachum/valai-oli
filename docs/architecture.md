# Valaioli — Architecture

## System overview

Valaioli is a three-layer application:

```
Browser (React + TypeScript)
        │  HTTP/JSON (REST)
        ▼
FastAPI backend (Python)
        │  subprocess (arg arrays, no shell)
        ▼
yt-dlp + FFmpeg (resolved from media-tools.lock.json)
```

### Component responsibilities

| Component | Responsibility |
|---|---|
| **Frontend** | URL input, metadata display, format selection, job progress, error states |
| **Backend API** | URL validation, metadata retrieval, job lifecycle, file delivery |
| **JobService** | Background task queue, progress tracking, cancellation |
| **ManifestService** | Reads `config/media-tools.lock.json`, resolves binary paths |
| **URLValidator** | Strict allowlist-based YouTube URL canonicalisation |
| **Dependency Updater** | Scheduled checks, candidate verification, staged installation, rollback |

---

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Service liveness check |
| GET | `/api/tools` | Active tool versions (read-only) |
| POST | `/api/metadata` | Fetch YouTube metadata and format list |
| POST | `/api/jobs` | Create a download job |
| GET | `/api/jobs/{id}` | Poll job status and progress |
| POST | `/api/jobs/{id}/cancel` | Cancel a running job |
| GET | `/api/jobs/{id}/download` | Stream completed output |

---

## Security model

### URL validation
- Only `https://www.youtube.com/watch?v=<id>` and `https://youtu.be/<id>` patterns are accepted.
- All query parameters except `v` are stripped.
- Video IDs are validated against a strict regex (`[A-Za-z0-9_-]{11}`).
- Private network ranges, localhost, and cloud metadata endpoints are blocked.

### Subprocess security
- `yt-dlp` and `ffmpeg` are invoked with argument **arrays** — never shell strings.
- Binary paths are resolved from the manifest; users cannot supply executable paths.
- Subprocess output size and execution time are bounded.
- User-supplied data is never interpolated into command arguments.

### File delivery
- Completed outputs are served under a short-lived token.
- Path traversal is prevented through sanitised filename generation.
- Temporary files are cleaned up on a configurable retention policy.

### Dependency management
- The public API cannot trigger installation or modification of media tools.
- Installation requires explicit operator approval via interactive prompt.
- Dependency permissions are separated from media-download permissions.

---

## Configuration

The backend reads all runtime configuration from:
- `config/media-tools.lock.json` — active tool versions (written by updater scripts only)
- Environment variables — port, CORS origins, temp-directory, retention policy

---

## Job lifecycle

```
POST /api/jobs
     │
     ▼ queued
     │
     ▼ downloading  (yt-dlp subprocess)
     │
     ▼ merging      (ffmpeg — if separate A/V streams)
     │
     ▼ converting   (ffmpeg — if audio format conversion requested)
     │
     ▼ validating   (ffprobe checks output integrity)
     │
     ▼ completed ──► GET /api/jobs/{id}/download
     │
     ▼ failed / cancelled
```
