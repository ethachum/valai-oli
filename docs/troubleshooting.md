# Valaioli — Troubleshooting

## Backend won't start

**Symptom:** `uvicorn` fails to start or exits immediately.

**Check:**
```powershell
cd backend
python -c "import fastapi, uvicorn; print('OK')"
```
If that fails, re-run `pip install -r requirements.txt` in the active virtual environment.

---

## `/api/tools` returns `null` active versions

This is expected until media tools have been installed.
Run the install workflow described in [`installation.md`](installation.md).

---

## yt-dlp installer fails with "GnuPG is required"

Install [Gpg4win](https://gpg4win.org/) and ensure `gpg.exe` is on your `PATH`.

---

## yt-dlp installer fails with "Set trustedSignerFingerprint"

Set the official yt-dlp signing-key fingerprint in `config/media-tools.lock.json`.
See [`installation.md`](installation.md) for the one-time GnuPG setup procedure.
Never use a fingerprint downloaded alongside the binary.

---

## Scheduled tasks not running

Check Task Scheduler history for `Valaioli - yt-dlp stable check` and
`Valaioli - FFmpeg stable check`. Common causes:
- PowerShell execution policy (`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`)
- Stale script path if the repository was moved
- `StartWhenAvailable` means missed checks run when the machine is next available

Re-register tasks after moving the repository:
```powershell
.\scripts\dependency-updater\register-scheduled-tasks.ps1
```

---

## Rollback fails with "Previous version binary missing"

The `tools/versions/` directory may have been cleaned up.
Re-run `install-candidate.ps1` for the target version to restore it,
or manually place the binary in `tools/versions/<tool>/<version>/`.

---

## Frontend cannot reach the backend

Ensure the backend is running on port 8000 and that the Vite dev server
proxy or CORS origin (`http://localhost:5173`) is allowed.
Check `app/main.py` `allow_origins` for the development configuration.

---

## FFmpeg merge step fails during download

The active FFmpeg version may be corrupt or missing.
Run `verify-tools.ps1` to check integrity.
If verification fails, use `rollback-tools.ps1 -Tool ffmpeg` or reinstall.
