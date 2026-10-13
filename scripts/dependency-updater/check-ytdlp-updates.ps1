[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-ValaioliLogging 'check-ytdlp'
Enter-ValaioliLock
try {
    $m = Read-ValaioliManifest
    $installed = Get-ActiveVersion $m 'ytDlp'
    Write-Log "Checking official yt-dlp stable release metadata. Installed version: $installed"
    $release = Invoke-TrustedGet $m.ytDlp.apiLatest
    if ($release.draft -or $release.prerelease) { throw 'Latest endpoint returned a draft/prerelease; refusing candidate.' }
    if ($release.tag_name -notmatch '^\d{4}\.\d{2}\.\d{2}(\.\d+)?$') { throw "Unexpected stable tag format: $($release.tag_name)" }
    $asset = @($release.assets | Where-Object { $_.name -eq 'yt-dlp.exe' }) | Select-Object -First 1
    $sums = @($release.assets | Where-Object { $_.name -eq 'SHA2-256SUMS' }) | Select-Object -First 1
    $sig = @($release.assets | Where-Object { $_.name -eq 'SHA2-256SUMS.sig' }) | Select-Object -First 1
    if (-not $asset -or -not $sums -or -not $sig) { throw 'Expected yt-dlp.exe, SHA2-256SUMS, or signature asset is missing.' }
    foreach ($a in @($asset,$sums,$sig)) {
        if ([uri]$a.browser_download_url -and ([uri]$a.browser_download_url).Host -ne 'github.com') { throw "Unexpected asset host: $($a.browser_download_url)" }
    }
    $comparison = Compare-ReleaseVersion $release.tag_name $installed
    $notes = [string]$release.body
    if ($notes.Length -gt 12000) { $notes = $notes.Substring(0,12000) + "`n[truncated]" }
    if ($comparison -gt 0) {
        $candidate = @{ version=$release.tag_name; releaseUrl=$release.html_url; publishedAt=$release.published_at; releaseNotes=$notes; assetName='yt-dlp.exe'; assetUrl=$asset.browser_download_url; checksumAssetUrl=$sums.browser_download_url; signatureAssetUrl=$sig.browser_download_url; checkedAtUtc=[DateTime]::UtcNow.ToString('o'); status='available-not-downloaded' }
        Set-CheckResult $m 'ytDlp' 'update-available' $candidate
        Write-Log "Stable update available: $($release.tag_name). No binary downloaded or installed. Release: $($release.html_url)" 'WARN'
    } else {
        Set-CheckResult $m 'ytDlp' 'up-to-date' $null
        Write-Log "No newer stable release. Latest upstream: $($release.tag_name); installed: $installed."
    }
} catch {
    Write-Log "Check failed; active binary was not changed. $($_.Exception.Message)" 'ERROR'
    try { $m = Read-ValaioliManifest; $m.ytDlp.lastCheckUtc=[DateTime]::UtcNow.ToString('o'); $m.ytDlp.lastOutcome='check-failed'; Save-ValaioliManifest $m } catch {}
    exit 1
} finally { Exit-ValaioliLock }
