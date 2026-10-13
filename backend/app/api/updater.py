"""
Valaioli — Updater status and verification endpoints

GET  /api/updater/status   Read candidate/active versions from manifest
POST /api/updater/verify   Run verify-tools.ps1 (read-only health check)

These endpoints are read-only or trigger safe read-only scripts.
No endpoint here can install, activate, or rollback a tool version —
those operations require manual operator interaction with the PS scripts.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services.manifest import ManifestService
from app.api._deps import get_manifest_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["updater"])

# Repository root — two levels above backend/app/api/
_REPO_ROOT = Path(__file__).resolve().parents[3]
_VERIFY_SCRIPT = _REPO_ROOT / "scripts" / "dependency-updater" / "verify-tools.ps1"


# ── Response schemas ──────────────────────────────────────────────────────────

class CandidateInfo(BaseModel):
    version: str | None
    status: str | None
    release_url: str | None
    checked_at_utc: str | None


class ToolUpdateStatus(BaseModel):
    name: str
    active_version: str | None
    last_check_utc: str | None
    last_outcome: str | None
    candidate: CandidateInfo | None


class UpdaterStatusResponse(BaseModel):
    tools: list[ToolUpdateStatus]
    update_available: bool     # True if any tool has a newer candidate


class VerifyResult(BaseModel):
    passed: bool
    output: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/updater/status", response_model=UpdaterStatusResponse)
async def updater_status(
    manifest: ManifestService = Depends(get_manifest_service),
) -> UpdaterStatusResponse:
    """
    Return the current update status for yt-dlp and FFmpeg.

    Reads the manifest directly; never triggers a network check.
    The scheduled check scripts write candidate data — this endpoint only reads it.
    """
    try:
        data = manifest._load()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Manifest not found. Run the dependency updater setup.")

    tools: list[ToolUpdateStatus] = []
    update_available = False

    for tool_key, display_name in [("ytDlp", "yt-dlp"), ("ffmpeg", "ffmpeg")]:
        tool_data = data.get(tool_key, {})
        candidate_raw = tool_data.get("candidate")
        candidate: CandidateInfo | None = None

        if candidate_raw and isinstance(candidate_raw, dict):
            candidate = CandidateInfo(
                version=candidate_raw.get("version"),
                status=candidate_raw.get("status"),
                release_url=candidate_raw.get("releaseUrl") or candidate_raw.get("providerUrl"),
                checked_at_utc=candidate_raw.get("checkedAtUtc"),
            )

        outcome = tool_data.get("lastOutcome") or "not-checked"
        active_ver = tool_data.get("activeVersion")

        if outcome == "update-available" and candidate:
            update_available = True

        tools.append(ToolUpdateStatus(
            name=display_name,
            active_version=active_ver,
            last_check_utc=tool_data.get("lastCheckUtc"),
            last_outcome=outcome,
            candidate=candidate,
        ))

    return UpdaterStatusResponse(tools=tools, update_available=update_available)


@router.post("/updater/verify", response_model=VerifyResult)
async def verify_tools(
    manifest: ManifestService = Depends(get_manifest_service),
) -> VerifyResult:
    """
    Run verify-tools.ps1 to health-check active binary versions against the manifest.

    This is a read-only operation — it never downloads, installs, or modifies anything.
    Returns the script output and whether all checks passed.
    """
    if not _VERIFY_SCRIPT.exists():
        raise HTTPException(status_code=503, detail=f"Verify script not found at {_VERIFY_SCRIPT}")

    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="Tool verification via PowerShell is only supported on Windows.")

    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "RemoteSigned",
            "-File", str(_VERIFY_SCRIPT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(_REPO_ROOT),
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout_bytes.decode("utf-8", errors="replace")
        passed = proc.returncode == 0
        logger.info("verify-tools.ps1 exit=%d passed=%s", proc.returncode, passed)
        return VerifyResult(passed=passed, output=output)

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Verification timed out after 30 seconds.")
    except Exception as exc:
        logger.exception("verify-tools.ps1 failed")
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}") from exc
