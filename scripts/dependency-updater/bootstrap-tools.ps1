<#
.SYNOPSIS
    Valaioli Bootstrap -- download and activate yt-dlp + FFmpeg without requiring GPG.

.DESCRIPTION
    Downloads yt-dlp.exe and FFmpeg from their official sources, verifies SHA-256
    checksums (yt-dlp via its published SHA2-256SUMS file; FFmpeg via gyan.dev hash),
    installs them into tools/versions/, and activates them in the manifest.

    NOTE: This does NOT verify the GPG signature on yt-dlp checksum file.
    Use install-candidate.ps1 (which requires Gpg4win) for full signature verification.
    This script is intended for first-time bootstrap where GPG is not yet installed.
#>
[CmdletBinding()]
param(
    [switch]$YtDlpOnly,
    [switch]$FfmpegOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-ValaioliLogging 'bootstrap-tools'
Enter-ValaioliLock

function Bootstrap-YtDlp {
    param([hashtable]$Manifest)

    $ytDlpData = $Manifest['ytDlp']
    $candidate = $ytDlpData['candidate']
    if (-not $candidate -or [string]::IsNullOrWhiteSpace([string]$candidate['version'])) {
        throw "No yt-dlp candidate in manifest. Run check-ytdlp-updates.ps1 first."
    }
    $version = [string]$candidate['version']
    Write-Log "Bootstrapping yt-dlp $version"

    # Fetch release metadata from GitHub
    $apiUrl = [string]$Manifest['ytDlp']['apiLatest']
    Write-Log "Fetching release metadata from $apiUrl"
    $release = Invoke-TrustedGet $apiUrl

    if ($release.tag_name -ne $version) {
        Write-Log "WARNING: Manifest candidate $version differs from latest GitHub tag $($release.tag_name). Using GitHub latest." 'WARN'
        $version = $release.tag_name
    }

    $assets = @{}
    foreach ($a in $release.assets) { $assets[$a.name] = $a.browser_download_url }

    foreach ($required in @('yt-dlp.exe', 'SHA2-256SUMS')) {
        if (-not $assets.ContainsKey($required)) { throw "Missing release asset: $required" }
    }

    # Download to staging
    $stageRoot = Get-RootedPath 'staging'
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
    $stage = Join-Path $stageRoot ("yt-dlp-{0}-bootstrap" -f $version)
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    Write-Log "Downloading yt-dlp.exe..."
    Invoke-TrustedWebRequest $assets['yt-dlp.exe'] (Join-Path $stage 'yt-dlp.exe')
    Write-Log "Downloading SHA2-256SUMS..."
    Invoke-TrustedWebRequest $assets['SHA2-256SUMS'] (Join-Path $stage 'SHA2-256SUMS')

    # Verify checksum
    $sumText = Get-Content -LiteralPath (Join-Path $stage 'SHA2-256SUMS') -Raw
    $line = @($sumText -split "`r?`n" | Where-Object { $_ -match '^[a-fA-F0-9]{64}\s+\*?yt-dlp\.exe\s*$' }) | Select-Object -First 1
    if (-not $line) { throw 'yt-dlp.exe checksum entry missing from SHA2-256SUMS.' }
    $expected = ($line -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath (Join-Path $stage 'yt-dlp.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "yt-dlp.exe SHA-256 mismatch. Expected $expected got $actual" }
    Write-Log "SHA-256 verified: $actual"

    # Smoke test
    $reported = (& (Join-Path $stage 'yt-dlp.exe') --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "yt-dlp smoke test failed: $reported" }
    Write-Log "yt-dlp --version: $reported"

    # Install
    $versionsRoot = Get-RootedPath 'tools/versions'
    $dest = Join-Path $versionsRoot "yt-dlp/$version"
    if (Test-Path $dest) {
        Write-Log "Version directory already exists: $dest -- skipping copy, just activating." 'WARN'
    } else {
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $stage 'yt-dlp.exe') -Destination (Join-Path $dest 'yt-dlp.exe')
        Write-Log "Installed yt-dlp.exe to $dest"
    }

    # Update manifest
    $Manifest['ytDlp']['previousVersion'] = $Manifest['ytDlp']['activeVersion']
    $Manifest['ytDlp']['activeVersion'] = $version
    $Manifest['ytDlp']['activeSha256'] = $actual
    $Manifest['ytDlp']['lastOutcome'] = 'installed-bootstrap'
    if ($Manifest['ytDlp']['candidate']) {
        $Manifest['ytDlp']['candidate']['status'] = 'installed'
    }
    Write-Log "yt-dlp $version activated."
}

function Bootstrap-Ffmpeg {
    param([hashtable]$Manifest)

    $ffmpegData = $Manifest['ffmpeg']
    $candidate = $ffmpegData['candidate']
    if (-not $candidate -or [string]::IsNullOrWhiteSpace([string]$candidate['version'])) {
        throw "No FFmpeg candidate in manifest. Run check-ffmpeg-updates.ps1 first."
    }
    $version = [string]$candidate['version']
    Write-Log "Bootstrapping FFmpeg $version"

    $archiveUrl = [string]$ffmpegData['archiveUrl']
    $checksumUrl = [string]$ffmpegData['checksumUrl']

    $u = [uri]$archiveUrl
    if ($u.Scheme -ne 'https' -or $u.Host -ne 'www.gyan.dev' -or $u.AbsolutePath -ne '/ffmpeg/builds/ffmpeg-release-essentials.zip') {
        throw "FFmpeg archive URL does not match the allowed gyan.dev artifact."
    }

    $stageRoot = Get-RootedPath 'staging'
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
    $stage = Join-Path $stageRoot ("ffmpeg-{0}-bootstrap" -f $version)
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    Write-Log "Downloading FFmpeg archive (~120 MB, this may take a few minutes)..."
    $archivePath = Join-Path $stage 'ffmpeg-release-essentials.zip'
    Invoke-TrustedWebRequest $archiveUrl $archivePath

    Write-Log "Downloading SHA-256 checksum..."
    $checksumPath = Join-Path $stage 'candidate.sha256'
    Invoke-TrustedWebRequest $checksumUrl $checksumPath

    # Verify checksum
    $checksumText = Get-Content $checksumPath -Raw
    if ($checksumText -notmatch '(?i)(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])') {
        throw "Gyan.dev SHA-256 file did not contain a valid digest."
    }
    $expected = $Matches[0].ToLowerInvariant()
    $actual = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "FFmpeg archive SHA-256 mismatch. Expected $expected got $actual" }
    Write-Log "SHA-256 verified: $actual"

    # Extract
    Write-Log "Extracting archive..."
    $expandPath = Join-Path $stage 'expanded'
    Expand-Archive -LiteralPath $archivePath -DestinationPath $expandPath -Force

    $ffmpegExe  = Get-ChildItem -LiteralPath $expandPath -Filter 'ffmpeg.exe'  -File -Recurse | Select-Object -First 1
    $ffprobeExe = Get-ChildItem -LiteralPath $expandPath -Filter 'ffprobe.exe' -File -Recurse | Select-Object -First 1
    if (-not $ffmpegExe -or -not $ffprobeExe) { throw 'ffmpeg.exe/ffprobe.exe not found in archive.' }

    # Smoke tests
    $reported = (& $ffmpegExe.FullName -version 2>&1 | Select-Object -First 1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "FFmpeg smoke test failed: $reported" }
    Write-Log "ffmpeg -version: $reported"

    # Synthetic media test
    $testOut = Join-Path $stage 'smoke-test.mp4'
    & $ffmpegExe.FullName -hide_banner -loglevel error -f lavfi -i 'color=c=black:s=64x64:d=0.2' -frames:v 1 -y $testOut
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $testOut)) { throw 'FFmpeg synthetic media smoke test failed.' }
    Write-Log "FFmpeg synthetic media test passed."

    # Install
    $versionsRoot = Get-RootedPath 'tools/versions'
    $dest = Join-Path $versionsRoot "ffmpeg/$version"
    if (Test-Path $dest) {
        Write-Log "Version directory already exists: $dest -- skipping copy, just activating." 'WARN'
    } else {
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        $binSrc = $ffmpegExe.Directory.FullName
        Copy-Item -LiteralPath $binSrc -Destination (Join-Path $dest 'bin') -Recurse
        Write-Log "Installed FFmpeg to $dest\bin"
    }

    # Update manifest
    $Manifest['ffmpeg']['previousVersion'] = $Manifest['ffmpeg']['activeVersion']
    $Manifest['ffmpeg']['activeVersion'] = $version
    $Manifest['ffmpeg']['activeArchiveSha256'] = $actual
    $Manifest['ffmpeg']['lastOutcome'] = 'installed-bootstrap'
    if ($Manifest['ffmpeg']['candidate']) {
        $Manifest['ffmpeg']['candidate']['status'] = 'installed'
    }
    Write-Log "FFmpeg $version activated."
}

try {
    $m = Read-ValaioliManifest

    if (-not $FfmpegOnly) {
        Bootstrap-YtDlp $m
        Save-ValaioliManifest $m
    }

    if (-not $YtDlpOnly) {
        Bootstrap-Ffmpeg $m
        Save-ValaioliManifest $m
    }

    Write-Log "Bootstrap complete. Restart the backend server to pick up the new tools."
    Write-Host ""
    Write-Host "Done! yt-dlp and FFmpeg are now installed and active." -ForegroundColor Green
} catch {
    Write-Log "Bootstrap failed: $($_.Exception.Message)" 'ERROR'
    Write-Host ""
    Write-Host "Bootstrap failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Exit-ValaioliLock
}
