[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
# Scripts live in scripts/dependency-updater/ — two levels below the repository root.
$root=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$manifest=Get-Content (Join-Path $root 'config/media-tools.lock.json') -Raw | ConvertFrom-Json
if ($manifest.schemaVersion -ne 1) { throw 'Unexpected manifest schema version.' }
if ($manifest.policy.approvalRequired -ne $true -or $manifest.policy.automaticInstallation -ne $false) { throw 'Unsafe policy settings.' }
if ($manifest.ytDlp.channel -ne 'stable') { throw 'yt-dlp must be stable channel.' }
if ($manifest.ffmpeg.archiveUrl -ne 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip') { throw 'FFmpeg URL allowlist mismatch.' }
if ($manifest.ffmpeg.checksumUrl -ne 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256') { throw 'FFmpeg checksum URL allowlist mismatch.' }
foreach ($tool in @($manifest.ytDlp,$manifest.ffmpeg)) {
    if ($tool.candidate -and $tool.candidate.version -and $tool.candidate.version -match '[\\/:]') { throw 'Candidate version contains path characters.' }
}
Write-Host 'Updater manifest/policy tests passed. (PowerShell runtime tests still required on Windows.)'
