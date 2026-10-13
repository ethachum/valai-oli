# Valaioli Android — Release Guide

## Version Tag Convention

Valaioli uses semantic versioning. Tag a stable release as:
```
v1.0.0
v1.1.0
v1.2.3
```

## Required GitHub Actions Secrets

Configure these in: **Repository → Settings → Secrets and variables → Actions**

| Secret | Description |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | Base64-encoded JKS or PKCS12 keystore file |
| `ANDROID_KEY_ALIAS` | Key alias within the keystore |
| `ANDROID_KEY_PASSWORD` | Private key password |
| `ANDROID_STORE_PASSWORD` | Keystore store password |

## Generating a Signing Keystore (one-time setup)

```powershell
keytool -genkey -v `
  -keystore valaioli.keystore `
  -alias valaioli `
  -keyalg RSA -keysize 4096 `
  -validity 10000 `
  -dname "CN=Valaioli, O=Valaioli, C=IN"

# Encode to base64 for the GitHub secret
[Convert]::ToBase64String([IO.File]::ReadAllBytes("valaioli.keystore")) | Set-Clipboard
```

Store the keystore file securely outside the repository. **Never commit it to source control.**

## Publishing a Release

```powershell
# 1. Update versionCode and versionName in android/app/build.gradle
# 2. Run the full test suite locally
cd valaioli-app\backend
.\.venv\Scripts\python.exe -m pytest tests/ -v

# 3. Tag and push
git tag v1.0.0
git push origin v1.0.0
```

The `android-release-build` workflow will:
1. Build the signed release APK
2. Calculate SHA-256 checksums
3. Write `release-manifest.json`
4. Create a **draft** GitHub Release (requires human approval to publish)

## APK Artifact Names

| Artifact | Description |
|---|---|
| `Valaioli-Android-v1.0.0-release.apk` | Universal signed release APK |
| `SHA256SUMS.txt` | SHA-256 checksums for all APKs |
| `release-manifest.json` | Machine-readable build metadata |

## Verifying a Release APK Checksum

```powershell
# Windows PowerShell
Get-FileHash -Algorithm SHA256 .\Valaioli-Android-v1.0.0-release.apk
# Compare with SHA256SUMS.txt

# Linux / macOS
sha256sum -c SHA256SUMS.txt
```
