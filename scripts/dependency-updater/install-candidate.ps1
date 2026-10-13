[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('yt-dlp','ffmpeg')][string]$Tool,
    [switch]$Approve
)
. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-ValaioliLogging 'install-candidate'
Enter-ValaioliLock
$stage = $null
try {
    $m = Read-ValaioliManifest
    $key = if ($Tool -eq 'yt-dlp') { 'ytDlp' } else { 'ffmpeg' }
    $candidate = $m[$key].candidate
    if (-not $candidate -or [string]::IsNullOrWhiteSpace([string]$candidate.version)) { throw "No candidate recorded for $Tool. Run its check script first." }
    $version = [string]$candidate.version
    if ($version -notmatch '^[0-9A-Za-z][0-9A-Za-z._-]{0,40}$') { throw 'Candidate version contains unexpected characters.' }
    $stageRoot = Get-RootedPath 'staging'
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
    $stage = Join-Path $stageRoot ("{0}-{1}-{2}" -f $Tool,$version,[guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    $versionsRoot = Get-RootedPath 'tools/versions'
    if ($Tool -eq 'yt-dlp') {
        # Re-resolve from official GitHub metadata; never trust a manifest-provided URL.
        $release = Invoke-TrustedGet $m.ytDlp.apiLatest
        if ($release.tag_name -ne $version -or $release.draft -or $release.prerelease) { throw 'Candidate is no longer the current official stable release; run check again.' }
        $assets = @{}
        foreach ($a in $release.assets) { $assets[$a.name] = $a.browser_download_url }
        foreach ($required in @('yt-dlp.exe','SHA2-256SUMS','SHA2-256SUMS.sig')) { if (-not $assets.ContainsKey($required)) { throw "Missing official release asset: $required" } }
        foreach ($name in @('yt-dlp.exe','SHA2-256SUMS','SHA2-256SUMS.sig')) {
            $uri=[uri]$assets[$name]
            if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'github.com' -or $uri.AbsolutePath -notmatch '^/yt-dlp/yt-dlp/releases/download/') { throw "Refusing unexpected official asset URL: $uri" }
            Invoke-TrustedWebRequest $uri.AbsoluteUri (Join-Path $stage $name)
        }
        $fingerprint = [string]$m.ytDlp.trustedSignerFingerprint
        if ($fingerprint -notmatch '^[A-Fa-f0-9]{40,64}$') { throw 'Set ytDlp.trustedSignerFingerprint after independently verifying the official yt-dlp signing-key fingerprint. Refusing unsigned/unverified installation.' }
        $gpg = Get-Command gpg.exe -ErrorAction SilentlyContinue
        if (-not $gpg) { $gpg = Get-Command gpg -ErrorAction SilentlyContinue }
        if (-not $gpg) { throw 'GnuPG is required to verify SHA2-256SUMS.sig. Install Gpg4win and retry.' }
        $status = & $gpg.Source --status-fd 1 --verify (Join-Path $stage 'SHA2-256SUMS.sig') (Join-Path $stage 'SHA2-256SUMS') 2>&1 | Out-String
        $validSigLine = @($status -split "`r?`n" | Where-Object { $_ -match '\[GNUPG:\] VALIDSIG ' }) | Select-Object -First 1
        $validFields = if ($validSigLine) { $validSigLine -split '\s+' } else { @() }
        $signingFingerprint = if ($validFields.Count -ge 3) { $validFields[2] } else { '' }
        $primaryFingerprint = if ($validFields.Count -ge 3) { $validFields[-1] } else { '' }
        $fingerprintMatches = ($signingFingerprint -ieq $fingerprint -or $primaryFingerprint -ieq $fingerprint)
        if ($LASTEXITCODE -ne 0 -or -not $validSigLine -or -not $fingerprintMatches) { throw "yt-dlp checksum signature verification failed or signer fingerprint did not match. $status" }
        $sumText = Get-Content -LiteralPath (Join-Path $stage 'SHA2-256SUMS') -Raw
        $line = @($sumText -split "`r?`n" | Where-Object { $_ -match '^[a-fA-F0-9]{64}\s+\*?yt-dlp\.exe\s*$' }) | Select-Object -First 1
        if (-not $line) { throw 'yt-dlp.exe checksum entry missing from signed SHA2-256SUMS.' }
        $expected = ($line -split '\s+')[0].ToLowerInvariant()
        $actual = (Get-FileHash -LiteralPath (Join-Path $stage 'yt-dlp.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) { throw 'yt-dlp.exe SHA-256 mismatch.' }
        $reported = (& (Join-Path $stage 'yt-dlp.exe') --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or $reported -ne $version) { throw "yt-dlp candidate smoke test failed: $reported" }
        $dest = Join-Path $versionsRoot ("yt-dlp/{0}" -f $version)
        if (Test-Path $dest) { throw "Version directory already exists: $dest. Inspect it manually; refusing overwrite." }
        New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
        Write-Log "yt-dlp artifact signature and SHA-256 verified; --version returned $reported."
        $candidateHash = $actual
        $candidatePath = $dest
    } else {
        # Fixed allow-listed Gyan.dev release-essentials URLs; no user-supplied URL is accepted.
        $uri=[uri]$m.ffmpeg.archiveUrl
        if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'www.gyan.dev' -or $uri.AbsolutePath -ne '/ffmpeg/builds/ffmpeg-release-essentials.zip') { throw 'FFmpeg archive URL does not match the allow-listed stable Gyan.dev artifact.' }
        $versionFile = Join-Path $stage 'candidate.ver'
        $checksumFile = Join-Path $stage 'candidate.sha256'
        $archive = Join-Path $stage 'ffmpeg-release-essentials.zip'
        Invoke-TrustedWebRequest $m.ffmpeg.versionUrl $versionFile
        $rawVersion=(Get-Content $versionFile -Raw).Trim()
        if ($rawVersion -notmatch '(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)') { throw "Cannot parse FFmpeg version metadata: $rawVersion" }
        if ($Matches[1] -ne $version) { throw 'FFmpeg candidate has changed upstream; run the check script again.' }
        Invoke-TrustedWebRequest $m.ffmpeg.checksumUrl $checksumFile
        Invoke-TrustedWebRequest $m.ffmpeg.archiveUrl $archive
        $checksumText=Get-Content $checksumFile -Raw
        if ($checksumText -notmatch '(?i)(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])') { throw 'Gyan.dev SHA-256 file did not contain a valid digest.' }
        $expected=$Matches[0].ToLowerInvariant()
        $actual=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $expected) { throw 'FFmpeg archive SHA-256 mismatch.' }
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $stage 'expanded') -Force
        $ffmpegExe=Get-ChildItem -LiteralPath (Join-Path $stage 'expanded') -Filter 'ffmpeg.exe' -File -Recurse | Select-Object -First 1
        $ffprobeExe=Get-ChildItem -LiteralPath (Join-Path $stage 'expanded') -Filter 'ffprobe.exe' -File -Recurse | Select-Object -First 1
        if (-not $ffmpegExe -or -not $ffprobeExe) { throw 'Expected ffmpeg.exe and ffprobe.exe not found in archive.' }
        $bin=$ffmpegExe.Directory.FullName
        $ffmpegOutput = & $ffmpegExe.FullName -version 2>&1
        $ffmpegExit = $LASTEXITCODE
        $reported = ($ffmpegOutput | Select-Object -First 1 | Out-String).Trim()
        if ($ffmpegExit -ne 0 -or $reported -notmatch [regex]::Escape("version $version")) { throw "FFmpeg candidate version smoke test failed: $reported" }
        
        $ffprobeOutput = & $ffprobeExe.FullName -version 2>&1
        $ffprobeExit = $LASTEXITCODE
        $probe = ($ffprobeOutput | Select-Object -First 1 | Out-String).Trim()
        if ($ffprobeExit -ne 0 -or $probe -notmatch 'ffprobe version') { throw "ffprobe smoke test failed: $probe" }
        # Synthetic local-media test; does not contact any website.
        $testOut=Join-Path $stage 'smoke-test.mp4'
        & $ffmpegExe.FullName -hide_banner -loglevel error -f lavfi -i 'color=c=black:s=64x64:d=0.2' -frames:v 1 -y $testOut
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $testOut)) { throw 'FFmpeg synthetic media smoke test failed.' }
        $dest=Join-Path $versionsRoot ("ffmpeg/{0}" -f $version)
        if (Test-Path $dest) { throw "Version directory already exists: $dest. Inspect it manually; refusing overwrite." }
        New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
        Write-Log "FFmpeg archive SHA-256 and version/synthetic-media tests passed. Note: provider-published hash is not a publisher signature."
        $candidateHash=$actual
        $candidatePath=$dest
    }
    Write-Log "Candidate $Tool $version is staged and verified. Active version remains unchanged until explicit approval."
    if (-not $Approve) {
        $answer=Read-Host "Type INSTALL to activate $Tool $version (previous version will be retained)"
        if ($answer -cne 'INSTALL') { Write-Log 'Approval not given; active version unchanged. Staged candidate retained for inspection.' 'WARN'; exit 2 }
    }
    if ($Tool -eq 'yt-dlp') {
        New-Item -ItemType Directory -Path $candidatePath -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $stage 'yt-dlp.exe') -Destination (Join-Path $candidatePath 'yt-dlp.exe')
        $m.ytDlp.previousVersion=$m.ytDlp.activeVersion
        $m.ytDlp.activeVersion=$version
        $m.ytDlp.activeSha256=$candidateHash
        $m.ytDlp.lastOutcome='installed-after-approval'
        $m.ytDlp.candidate.status='installed'
    } else {
        New-Item -ItemType Directory -Path $candidatePath -Force | Out-Null
        $bin=(Get-ChildItem -LiteralPath (Join-Path $stage 'expanded') -Filter 'ffmpeg.exe' -File -Recurse | Select-Object -First 1).Directory.FullName
        Copy-Item -LiteralPath $bin -Destination (Join-Path $candidatePath 'bin') -Recurse
        $m.ffmpeg.previousVersion=$m.ffmpeg.activeVersion
        $m.ffmpeg.activeVersion=$version
        $m.ffmpeg.activeArchiveSha256=$candidateHash
        $m.ffmpeg.lastOutcome='installed-after-approval'
        $m.ffmpeg.candidate.status='installed'
    }
    Save-ValaioliManifest $m
    Write-Log "Activated $Tool $version. Previous version retained: $($m[$key].previousVersion)"
} catch {
    Write-Log "Candidate rejected; active version not intentionally changed. $($_.Exception.Message)" 'ERROR'
    try { $m=Read-ValaioliManifest; $key=if($Tool -eq 'yt-dlp'){'ytDlp'}else{'ffmpeg'}; $m[$key].lastOutcome='install-failed'; Save-ValaioliManifest $m } catch {}
    exit 1
} finally {
    # Do not delete staging automatically: keep failed candidates and logs for diagnostics.
    Exit-ValaioliLock
}
