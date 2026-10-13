[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-ValaioliLogging 'verify-tools'
Enter-ValaioliLock
$failed = $false
try {
    $m = Read-ValaioliManifest
    foreach ($tool in @('ytDlp','ffmpeg')) {
        $v = Get-ActiveVersion $m $tool
        if ($v -eq 'unknown') { Write-Log "$tool has no active version recorded yet." 'WARN'; $failed=$true; continue }
        if ($tool -eq 'ytDlp') {
            $exe = Get-ActiveToolPath 'yt-dlp' $v 'yt-dlp.exe'
            if (-not $exe) { Write-Log "Missing active yt-dlp binary for version $v" 'ERROR'; $failed=$true; continue }
            $reported = (& $exe --version 2>&1 | Out-String).Trim()
            if ($LASTEXITCODE -ne 0 -or $reported -ne $v) { Write-Log "yt-dlp version check failed: expected $v, got $reported" 'ERROR'; $failed=$true } else { Write-Log "yt-dlp OK: $reported ($exe)" }
            if ($m.ytDlp.activeSha256) {
                $hash=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($hash -ne $m.ytDlp.activeSha256.ToLowerInvariant()) { Write-Log 'Active yt-dlp hash does not match manifest.' 'ERROR'; $failed=$true }
            }
        } else {
            $folder = Get-RootedPath ("tools/versions/ffmpeg/{0}/bin" -f $v)
            $ffmpeg = Join-Path $folder 'ffmpeg.exe'; $ffprobe=Join-Path $folder 'ffprobe.exe'
            if (-not (Test-Path $ffmpeg) -or -not (Test-Path $ffprobe)) { Write-Log "Missing active FFmpeg/ffprobe for version $v" 'ERROR'; $failed=$true; continue }
            $ffmpegOutput = & $ffmpeg -version 2>&1
            $ffmpegExit = $LASTEXITCODE
            $reported = ($ffmpegOutput | Select-Object -First 1 | Out-String).Trim()
            if ($ffmpegExit -ne 0 -or $reported -notmatch [regex]::Escape("version $v")) { Write-Log "FFmpeg version check failed: expected $v, got $reported" 'ERROR'; $failed=$true } else { Write-Log "FFmpeg OK: $reported" }
            $ffprobeOutput = & $ffprobe -version 2>&1
            $ffprobeExit = $LASTEXITCODE
            $probe = ($ffprobeOutput | Select-Object -First 1 | Out-String).Trim()
            if ($ffprobeExit -ne 0 -or $probe -notmatch 'ffprobe version') { Write-Log "ffprobe check failed: $probe" 'ERROR'; $failed=$true } else { Write-Log "ffprobe OK: $probe" }
        }
    }
    if ($failed) { Write-Log 'Verification failed.' 'ERROR'; exit 1 }
    Write-Log 'All configured active tools passed version checks.'
} catch { Write-Log $_.Exception.Message 'ERROR'; exit 1 }
finally { Exit-ValaioliLock }
