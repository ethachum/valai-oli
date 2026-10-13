# Valaioli — Dependency Update Workflow

This document describes the yt-dlp and FFmpeg update process, including
scheduled checks, candidate verification, approval, installation, and rollback.

---

## Principles

- Scheduled tasks perform **metadata-only checks**. They never download binaries.
- Installation is a **separate, manual command** requiring explicit operator approval.
- Every candidate is staged, verified, and smoke-tested before activation.
- The previous working version is always retained for immediate rollback.
- Logs record version, timestamps, outcomes, and any failures.

---

## yt-dlp update policy

| Setting | Value |
|---|---|
| Source | https://github.com/yt-dlp/yt-dlp/releases |
| Channel | Stable releases only |
| Check schedule | Monday and Thursday at 9:00 AM |
| Verification | GPG signature on checksum file; SHA-256 of binary against signed checksum |
| Signing key | Must be independently verified and set in `config/media-tools.lock.json` |

### Authenticity

The installer downloads `yt-dlp.exe`, `SHA2-256SUMS`, and `SHA2-256SUMS.sig`
from the official GitHub release. It:

1. Verifies the GPG signature on `SHA2-256SUMS`.
2. Checks that the signer fingerprint matches `ytDlp.trustedSignerFingerprint`.
3. Computes the SHA-256 of `yt-dlp.exe` and matches it against the signed checksum.
4. Runs `yt-dlp.exe --version` as a smoke test.

> **Important:** Never trust a signing key downloaded alongside the binary.
> Set `trustedSignerFingerprint` only after independently verifying it.

---

## FFmpeg update policy

| Setting | Value |
|---|---|
| Source | https://ffmpeg.org/download.html → Gyan.dev release-essentials |
| Channel | `release-essentials` stable builds |
| Check schedule | Monday at 9:00 AM |
| Verification | SHA-256 against provider-published checksum file |

### Trust limitation

The checksum is fetched from the same provider as the archive (Gyan.dev over HTTPS).
This detects accidental corruption and archive/checksum mismatches, but is **not**
equivalent to an independently authenticated publisher signature. Review the provider
and the candidate before approval.

---

## Workflow

### Automatic (scheduled)

```
Task Scheduler fires → check-ytdlp-updates.ps1 or check-ffmpeg-updates.ps1
                     → reads release metadata (no binary download)
                     → updates config/media-tools.lock.json with candidate info
                     → writes log to logs/
```

Check `logs/check-ytdlp-<date>.log` or `logs/check-ffmpeg-<date>.log` for outcomes.

### Manual installation

```powershell
# 1. Review the log and candidate release URL
#    (logs/check-ytdlp-YYYYMMDD.log)

# 2. Run the installer in an interactive window
.\scripts\dependency-updater\install-candidate.ps1 -Tool yt-dlp

# The script:
# - Re-fetches release metadata from GitHub (never trusts manifest URL)
# - Downloads yt-dlp.exe, SHA2-256SUMS, SHA2-256SUMS.sig to staging/
# - Verifies the GPG signature and SHA-256
# - Runs yt-dlp.exe --version
# - Asks you to type INSTALL
# - Moves the verified binary to tools/versions/yt-dlp/<version>/
# - Updates config/media-tools.lock.json activeVersion
# - Retains the previous version

# 3. Verify the active installation
.\scripts\dependency-updater\verify-tools.ps1
```

### Rollback

```powershell
.\scripts\dependency-updater\rollback-tools.ps1 -Tool yt-dlp
# Type ROLLBACK to confirm
```

Both version directories are retained on disk after rollback.

---

## Manifest schema (`config/media-tools.lock.json`)

```json
{
  "schemaVersion": 1,
  "policy": {
    "approvalRequired": true,
    "automaticInstallation": false,
    "releaseChannel": "stable"
  },
  "ytDlp": {
    "activeVersion": "2024.11.18",
    "previousVersion": "2024.10.07",
    "activeSha256": "...",
    "trustedSignerFingerprint": "<40-or-64-hex>",
    "candidate": { ... },
    "lastCheckUtc": "2024-11-21T09:00:00Z",
    "lastOutcome": "up-to-date"
  },
  "ffmpeg": {
    "activeVersion": "7.1",
    "previousVersion": "7.0.2",
    "candidate": { ... },
    "lastCheckUtc": "2024-11-18T09:00:00Z",
    "lastOutcome": "up-to-date"
  }
}
```

The backend resolves binary paths from `activeVersion` fields only.
It never reads candidate or previousVersion fields at runtime.

---

## Safety rules

1. Never run the installer from a scheduled task.
2. Never accept arbitrary artifact URLs from a user or release note.
3. Passing version/hash checks does not mean a release is safe — inspect release notes.
4. If a check fails, the active version remains unchanged.
5. Keep these scripts under version control; do not run modified scripts from untrusted branches.
