# Valaioli — Installation

## Prerequisites

| Tool | Minimum version | Purpose |
|---|---|---|
| Node.js | 20 LTS | Frontend dev server and build |
| npm | 10 | Package management |
| Python | 3.12 | Backend runtime |
| PowerShell | 5.1 or 7+ | Dependency updater scripts |
| Gpg4win / GnuPG | Any current | yt-dlp signature verification |

---

## 1 — Clone and configure

```powershell
git clone <repo-url> valaioli-app
cd valaioli-app
```

---

## 2 — Install media tools (yt-dlp and FFmpeg)

Media tools are **not bundled** in the repository. Install them through the Valaioli Dependency Updater.

### First-time GnuPG setup (required for yt-dlp)

1. Install [Gpg4win](https://gpg4win.org/).
2. Find the official yt-dlp signing-key fingerprint from a trusted source
   (see [yt-dlp release notes](https://github.com/yt-dlp/yt-dlp/releases) and the project's own signing instructions).
3. Import the official public key into your local keyring:
   ```
   gpg --recv-keys <FINGERPRINT>
   ```
4. Set the fingerprint in `config/media-tools.lock.json`:
   ```json
   "ytDlp": {
     "trustedSignerFingerprint": "<40-or-64-hex-char-fingerprint>"
   }
   ```
   > **Warning:** Never use a fingerprint that was downloaded alongside the binary.
   > Verify it independently through the official yt-dlp communication channels.

### Run metadata checks

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\dependency-updater\check-ytdlp-updates.ps1
.\scripts\dependency-updater\check-ffmpeg-updates.ps1
```

If updates are available, review the log in `logs/` and the release notes.

### Install a candidate

```powershell
.\scripts\dependency-updater\install-candidate.ps1 -Tool yt-dlp
.\scripts\dependency-updater\install-candidate.ps1 -Tool ffmpeg
```

Type `INSTALL` at the prompt to approve. The script stages, verifies, smoke-tests,
then activates the tool. The previous version is retained for rollback.

### Verify installation

```powershell
.\scripts\dependency-updater\verify-tools.ps1
```

---

## 3 — Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API documentation: http://localhost:8000/api/docs

---

## 4 — Frontend

```powershell
cd frontend
npm install
npm run dev
```

UI: http://localhost:5173

---

## 5 — Register scheduled update checks

```powershell
# Run as the current user (interactive logon required)
.\scripts\dependency-updater\register-scheduled-tasks.ps1
```

This registers:
- **Valaioli - yt-dlp stable check** — Monday and Thursday at 9:00 AM
- **Valaioli - FFmpeg stable check** — Monday at 9:00 AM

The tasks perform **metadata-only checks**. They never download or install binaries.
Check `logs/` for outcomes after each scheduled run.

---

## Rollback

```powershell
.\scripts\dependency-updater\rollback-tools.ps1 -Tool yt-dlp
.\scripts\dependency-updater\rollback-tools.ps1 -Tool ffmpeg
```

Type `ROLLBACK` at the prompt. The previous version is immediately re-activated.
Both versions remain on disk.
