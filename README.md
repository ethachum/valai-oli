# Valaioli

**Valaioli** is a modern, open-source media downloader for YouTube content.
It runs on **Windows** (desktop web app) and **Android** (native APK).
Users select video resolutions, formats, and audio quality through a polished React interface.

> **Legal notice**: Users are responsible for downloading only media they own or
> are authorized to save, and for complying with applicable laws and service terms.
> Valaioli is not affiliated with YouTube or any other media provider.

---

## Platforms

| Platform | Technology | Media engine |
|---|---|---|
| **Desktop (Windows)** | React + Vite + FastAPI | yt-dlp.exe + ffmpeg.exe |
| **Android** | React + Vite + Capacitor + Kotlin | youtubedl-android (yt-dlp runtime, FFmpeg native) |

---

## Features

- Download YouTube videos (360p – 8K where available) and audio (MP3, M4A, WAV)
- Playlist support — select individual tracks or download the whole playlist
- Download history, cancellation, and queue management
- Progress notifications (Android foreground service)
- No hosted server required on Android — all processing runs on your device

---

## Project structure

```
valaioli-app/
├── frontend/               React + TypeScript + Vite web interface
│   ├── src/
│   │   ├── services/
│   │   │   ├── api.ts                 Platform-independent API facade
│   │   │   ├── engine/
│   │   │   │   ├── DownloadEngine.ts  Platform abstraction interface
│   │   │   │   ├── DesktopDownloadEngine.ts  → FastAPI backend
│   │   │   │   ├── AndroidDownloadEngine.ts  → ValaioliNative plugin
│   │   │   │   └── getEngine.ts       Runtime engine selector
│   │   │   └── native/
│   │   │       └── ValaioliNative.ts  Capacitor plugin type definitions
│   ├── android/                       Capacitor Android project
│   │   └── app/src/main/java/org/valaioli/app/
│   │       ├── MainActivity.kt
│   │       ├── ValaioliNativePlugin.kt
│   │       ├── DownloadService.kt
│   │       ├── AndroidStorageHelper.kt
│   │       └── ValaioliJob.kt
│   └── capacitor.config.ts
├── backend/                FastAPI media download service (Desktop)
├── scripts/
│   └── dependency-updater/ PowerShell scripts for desktop tool updates
├── config/
│   ├── media-tools.lock.json       Desktop tool versions
│   └── android-engine.manifest.json  Android engine versions
├── .github/
│   └── workflows/
│       ├── ci.yml                  Desktop CI (backend + frontend)
│       └── android-ci-release.yml  Android CI + release
├── docs/                   Full documentation
├── LICENSE                 GPL-3.0
└── THIRD_PARTY_NOTICES.md  Third-party dependency attributions
```

---

## Quick start — Desktop (Windows)

### Prerequisites

- **Node.js 20+** and **npm 10+**
- **Python 3.12+**
- **PowerShell 5.1+**
- **Gpg4win / GnuPG** (for yt-dlp signature verification)

### Run

```powershell
# Install and configure media tools first:
# See docs/installation.md

# Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

UI: http://localhost:5173 — API docs: http://localhost:8000/api/docs

---

## Quick start — Android APK

### Download and install

1. Go to the [**GitHub Releases**](https://github.com/YOUR_ORG/valaioli/releases) page
2. Download `Valaioli-Android-vX.X.X-release.apk`
3. Verify the checksum: `SHA256SUMS.txt`
4. On your device: **Settings → Security → Install unknown apps** → allow your file manager
5. Open the APK file and tap **Install**

### Build locally

See [`docs/android-development.md`](docs/android-development.md) for full instructions.

```powershell
cd frontend
npm ci
npm run build
npx cap sync android
cd android
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21.0.12.1"
.\gradlew.bat assembleDebug
# APK: android\app\build\outputs\apk\debug\app-debug.apk
```

### Supported Android versions and architectures

| | |
|---|---|
| **Minimum Android version** | Android 6.0 (API 23) |
| **Recommended** | Android 10+ (API 29+) for full Scoped Storage support |
| **Supported ABIs** | `arm64-v8a`, `armeabi-v7a`, `x86_64`, `x86` |

---

## Testing

```powershell
# Backend tests
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v    # 62 tests

# Frontend build check
cd frontend
npm run build
```

---

## Dependency update policy

| Tool | Schedule | Source |
|---|---|---|
| yt-dlp (desktop) | Monday & Thursday | Official yt-dlp GitHub releases |
| FFmpeg (desktop) | Monday | Official FFmpeg + reputable Windows build |
| youtubedl-android | Monday & Thursday | Maven Central — io.github.junkfood02 |

See [`docs/dependency-updates.md`](docs/dependency-updates.md) for full details.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | System overview, API design, security model |
| [`docs/installation.md`](docs/installation.md) | Desktop setup and configuration |
| [`docs/dependency-updates.md`](docs/dependency-updates.md) | Media tool update workflow |
| [`docs/troubleshooting.md`](docs/troubleshooting.md) | Desktop problems and solutions |
| [`docs/android-development.md`](docs/android-development.md) | Android build guide |
| [`docs/android-release.md`](docs/android-release.md) | Android release and signing |
| [`docs/android-troubleshooting.md`](docs/android-troubleshooting.md) | Android problems and solutions |

---

## Security

- All user-supplied URLs are validated on both the desktop backend and the Android native layer before any subprocess is invoked.
- Desktop: subprocess calls use argument arrays, never shell strings.
- Android: yt-dlp requests are built with the `YoutubeDLRequest` structured API — never string concatenation with user input.
- SSRF protection rejects private IP ranges and `file://` URLs.
- No analytics, trackers, account requirements, or mandatory remote APIs.

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).

Third-party attributions: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
