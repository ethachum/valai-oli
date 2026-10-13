[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidateSet('yt-dlp','ffmpeg')][string]$Tool,[switch]$Approve)
. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-ValaioliLogging 'rollback-tools'
Enter-ValaioliLock
try {
    $m=Read-ValaioliManifest
    $key=if($Tool -eq 'yt-dlp'){'ytDlp'}else{'ffmpeg'}
    $previous=[string]$m[$key].previousVersion
    if ([string]::IsNullOrWhiteSpace($previous)) { throw "No previous $Tool version recorded; cannot rollback." }
    if ($Tool -eq 'yt-dlp') {
        $p=Get-ActiveToolPath 'yt-dlp' $previous 'yt-dlp.exe'
        if (-not $p) { throw "Previous yt-dlp binary missing: $previous" }
        $v=(& $p --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $v -ne $previous) { throw "Previous yt-dlp binary failed version test: $v" }
    } else {
        $dir=Get-RootedPath ("tools/versions/ffmpeg/{0}/bin" -f $previous)
        $p=Join-Path $dir 'ffmpeg.exe'; $probe=Join-Path $dir 'ffprobe.exe'
        if (-not (Test-Path $p) -or -not (Test-Path $probe)) { throw "Previous FFmpeg binaries missing: $previous" }
        $v=(& $p -version 2>&1 | Select-Object -First 1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $v -notmatch [regex]::Escape("version $previous")) { throw "Previous FFmpeg binary failed version test: $v" }
    }
    if (-not $Approve) {
        $answer=Read-Host "Type ROLLBACK to activate previous $Tool version $previous"
        if ($answer -cne 'ROLLBACK') { Write-Log 'Rollback not approved; no changes made.' 'WARN'; exit 2 }
    }
    $current=$m[$key].activeVersion
    $m[$key].activeVersion=$previous
    $m[$key].previousVersion=$current
    $m[$key].lastOutcome='rolled-back-after-approval'
    Save-ValaioliManifest $m
    Write-Log "Rollback complete for $Tool: $current -> $previous"
} catch { Write-Log $_.Exception.Message 'ERROR'; exit 1 }
finally { Exit-ValaioliLock }
