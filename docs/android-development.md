# Valaioli Android — Development Guide

## Prerequisites

| Tool | Minimum Version | Purpose |
|---|---|---|
| Android Studio | Ladybug (2024.2) | IDE, emulator, APK signing |
| JDK | 21 (Temurin) | Gradle build toolchain |
| Node.js | 20 LTS | Frontend build |
| npm | 10+ | Package management |
| Android SDK | API 35 (compile), API 23 (min) | Android libraries |
| Android NDK | 27+ | Native library ABIs |

## Setting up Android Studio

1. Download [Android Studio](https://developer.android.com/studio) and install it.
2. Open SDK Manager → install **Android 15 (API 35)** SDK Platform + SDK Tools.
3. Install NDK via: **SDK Manager → SDK Tools → NDK (Side by side)**.
4. Set `ANDROID_HOME` environment variable to your SDK path:
   ```powershell
   [System.Environment]::SetEnvironmentVariable("ANDROID_HOME", "C:\Users\<you>\AppData\Local\Android\Sdk", "User")
   ```

## Building locally (Windows PowerShell)

```powershell
# 1. From the repo root, build the React frontend
cd valaioli-app\frontend
npm ci
npm run build

# 2. Sync Capacitor assets to the android project
npx cap sync android

# 3. Open in Android Studio (optional — for GUI)
npx cap open android

# 4. OR build debug APK from command line (requires ANDROID_HOME and JDK 21)
cd android
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21.0.12.1"
.\gradlew.bat assembleDebug
```

The debug APK will be at:
```
android\app\build\outputs\apk\debug\app-debug.apk
```

## Installing on a device

```powershell
# Enable USB debugging on the Android device, then:
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
```

Or simply copy the APK to the device and open it in a file manager.

## Architecture Overview

```
React/Vite frontend  (services/api.ts)
        │
        ▼
getDownloadEngine()  ─── platform check (Capacitor.isNativePlatform())
        │                  │
  DesktopDownloadEngine    AndroidDownloadEngine
  (calls FastAPI)          (calls ValaioliNative Capacitor plugin)
                                │
                     ValaioliNativePlugin.kt (Kotlin)
                                │
                     DownloadService.kt (Foreground Service)
                                │
                     youtubedl-android (yt-dlp Python runtime, FFmpeg)
                                │
                     AndroidStorageHelper (MediaStore / public dirs)
```

## Kotlin native plugin files

| File | Purpose |
|---|---|
| `MainActivity.kt` | Capacitor BridgeActivity entry point |
| `ValaioliNativePlugin.kt` | `@CapacitorPlugin` bridge between JS and Kotlin |
| `DownloadService.kt` | Foreground service: job queue, yt-dlp invocation, progress events |
| `AndroidStorageHelper.kt` | Scoped Storage: MediaStore (API 29+), legacy fallback |
| `ValaioliJob.kt` | Data class holding per-job state |

## Background download behaviour

`DownloadService` is a standard Android foreground service with a persistent notification. Android requires `FOREGROUND_SERVICE` and `FOREGROUND_SERVICE_DATA_SYNC` permissions (declared in `AndroidManifest.xml`). On Android 14+ the service type `dataSync` satisfies the user-initiated data transfer restrictions.

Downloads do **not** use WorkManager because yt-dlp requires long-running CPU time that WorkManager's per-task time limits (15 minutes) cannot guarantee for large downloads.

The OS may still kill the process under extreme memory pressure. Persisted job state in `DownloadService.jobs` is lost on process death. A full recovery implementation would persist the in-memory map to a Room database before each state transition, then reload it in `onCreate`. This is the main outstanding reliability improvement for a production release.

## Debugging

```powershell
# Stream logcat (filter to Valaioli tags)
adb logcat -s ValaioliDownload:D ValaioliStorage:D System.err:W
```
