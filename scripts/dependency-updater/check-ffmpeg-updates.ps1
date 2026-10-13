[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-ValaioliLogging 'check-ffmpeg'
Enter-ValaioliLock
try {
    $m = Read-ValaioliManifest
    $installed = Get-ActiveVersion $m 'ffmpeg'
    Write-Log "Checking Gyan.dev stable release essentials metadata (linked by FFmpeg's official download page). Installed version: $installed"
    $versionFile = Join-Path (Get-RootedPath 'staging') 'ffmpeg-version-check.txt'
    New-Item -ItemType Directory -Path (Split-Path $versionFile) -Force | Out-Null
    Invoke-TrustedWebRequest $m.ffmpeg.versionUrl $versionFile
    $raw = (Get-Content -LiteralPath $versionFile -Raw).Trim()
    if ($raw -notmatch '(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)') { throw "Could not parse stable FFmpeg version metadata: $raw" }
    $version = $Matches[1]
    $comparison = Compare-ReleaseVersion $version $installed
    if ($comparison -gt 0) {
        $candidate = @{ version=$version; releaseUrl=$m.ffmpeg.officialInfo; providerUrl=$m.ffmpeg.provider; assetUrl=$m.ffmpeg.archiveUrl; checksumUrl=$m.ffmpeg.checksumUrl; assetName='ffmpeg-release-essentials.zip'; checkedAtUtc=[DateTime]::UtcNow.ToString('o'); status='available-not-downloaded'; verification='provider-published-sha256-over-HTTPS; publisher signature not advertised for this Windows archive' }
        Set-CheckResult $m 'ffmpeg' 'update-available' $candidate
        Write-Log "Stable FFmpeg release candidate: $version. No archive downloaded or installed. Provider: $($m.ffmpeg.provider)" 'WARN'
    } else {
        Set-CheckResult $m 'ffmpeg' 'up-to-date' $null
        Write-Log "No newer stable FFmpeg essentials release. Latest upstream: $version; installed: $installed."
    }
} catch {
    Write-Log "Check failed; active binary was not changed. $($_.Exception.Message)" 'ERROR'
    try { $m = Read-ValaioliManifest; $m.ffmpeg.lastCheckUtc=[DateTime]::UtcNow.ToString('o'); $m.ffmpeg.lastOutcome='check-failed'; Save-ValaioliManifest $m } catch {}
    exit 1
} finally { Exit-ValaioliLock }
