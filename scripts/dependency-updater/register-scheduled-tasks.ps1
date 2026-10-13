[CmdletBinding()]
param([switch]$CurrentUserOnly)
$ErrorActionPreference='Stop'
# scripts live in scripts/dependency-updater/ — two levels below the repository root.
$root=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pwsh="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $pwsh)) { $pwsh='powershell.exe' }
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal=New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
$tasks=@(
    @{Name='Valaioli - yt-dlp stable check'; Script=(Join-Path $PSScriptRoot 'check-ytdlp-updates.ps1'); Days=@('Monday','Thursday')},
    @{Name='Valaioli - FFmpeg stable check'; Script=(Join-Path $PSScriptRoot 'check-ffmpeg-updates.ps1'); Days=@('Monday')}
)
foreach ($t in $tasks) {
    $triggers=@(foreach ($day in $t.Days) { New-ScheduledTaskTrigger -Weekly -DaysOfWeek $day -At '9:00AM' })
    $action=New-ScheduledTaskAction -Execute $pwsh -Argument ("-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File `"{0}`"" -f $t.Script) -WorkingDirectory $root
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'Checks Valaioli media tool release metadata only; never installs binaries.' -Force | Out-Null
    Write-Host "Registered $($t.Name) for $($t.Days -join ', ') at 9:00 AM local time."
}
Write-Host 'Tasks registered. Check Task Scheduler history and logs/ for outcomes.'
