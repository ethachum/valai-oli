# Valaioli Android — Troubleshooting

## "Engine not initialized" error in the app

The app shows this when `DownloadService` did not bind to the Capacitor plugin in time (first launch) or the service was killed.

**Fix:** Close and reopen the app. The service starts automatically in `MainActivity.onCreate`. If the error persists, check logcat:
```
adb logcat -s ValaioliDownload:E
```

## Download fails immediately on first URL

Most likely yt-dlp has not yet been initialised by the Android runtime on a fresh install.

**Fix:** Wait a few seconds and try again. The `initEngine` call happens asynchronously at app startup.

## "Storage error" or file not appearing in Downloads

On Android 10+, Valaioli writes to `MediaStore` (Music/Movies/Downloads). The file may take a few seconds to appear in the Files app due to MediaStore indexing delay.

Check that:
- The device is not in low-storage mode
- The app has not had its storage-related permissions revoked

## Notification does not appear (Android 13+)

Android 13 (API 33) requires the `POST_NOTIFICATIONS` runtime permission.

**Fix:** Go to **Settings → Apps → Valaioli → Notifications** and enable notifications, or allow the permission prompt when the app first requests it.

## Gradle build fails: "Could not download gradle-X.X.X-all.zip"

The Gradle wrapper cannot reach `services.gradle.org`.

**Fix:** Either connect to a network that allows outbound HTTPS to gradle.org, or configure a proxy in `gradle.properties`:
```properties
systemProp.https.proxyHost=your-proxy
systemProp.https.proxyPort=8080
```

## Signing secret not configured

The release workflow will fail with:
```
ANDROID_KEYSTORE_BASE64 secret is not set. Cannot produce signed release APK.
```
See [android-release.md](android-release.md) for keystore setup instructions.

## App crashes on launch (unsupported ABI)

The APK contains native `.so` libraries for `arm64-v8a`, `armeabi-v7a`, `x86_64`, and `x86`. If the device reports an ABI mismatch, it likely uses an unsupported architecture (very rare).

**Workaround:** Build an ABI-specific APK using Android App Bundle (`./gradlew bundleRelease`) and extract the correct APK from the bundle.

## Download stuck at 0% forever

Possible causes:
- Network blocked (try a different network or VPN)
- YouTube rate-limiting or IP block (common for datacenter/VPN IPs)
- yt-dlp needs updating (bundled version may be outdated)

yt-dlp self-updates are not yet implemented in v1.0. Update by installing a newer Valaioli APK release.
