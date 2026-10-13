Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ValaioliRoot {
    # Scripts live in scripts/dependency-updater/ — two levels below the repository root.
    return (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}
function Get-ValaioliManifestPath { Join-Path (Get-ValaioliRoot) 'config/media-tools.lock.json' }
function ConvertTo-HashtableDeep($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Collections.IDictionary]) {
        $result = @{}
        foreach ($key in $Value.Keys) { $result[$key] = ConvertTo-HashtableDeep $Value[$key] }
        return $result
    }
    if ($Value -is [pscustomobject]) {
        $result = @{}
        foreach ($property in $Value.PSObject.Properties) { $result[$property.Name] = ConvertTo-HashtableDeep $property.Value }
        return $result
    }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        $result = @()
        foreach ($item in $Value) { $result += ,(ConvertTo-HashtableDeep $item) }
        return ,$result
    }
    return $Value
}
function Read-ValaioliManifest {
    $p = Get-ValaioliManifestPath
    if (-not (Test-Path -LiteralPath $p)) { throw "Manifest not found: $p" }
    $parsed = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
    return (ConvertTo-HashtableDeep $parsed)
}
function Save-ValaioliManifest([hashtable]$Manifest) {
    $p = Get-ValaioliManifestPath
    $tmp = "$p.tmp"
    $backup = "$p.bak"
    $json = $Manifest | ConvertTo-Json -Depth 30
    [System.IO.File]::WriteAllText($tmp, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $p) {
        try { [System.IO.File]::Replace($tmp, $p, $backup, $true) }
        catch { Move-Item -LiteralPath $tmp -Destination $p -Force }
    } else { Move-Item -LiteralPath $tmp -Destination $p }
}
function Get-RootedPath([string]$RelativePath) { Join-Path (Get-ValaioliRoot) $RelativePath }
function Initialize-ValaioliLogging([string]$Name) {
    $logDir = Get-RootedPath 'logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $script:LogPath = Join-Path $logDir ("{0}-{1}.log" -f $Name, (Get-Date -Format 'yyyyMMdd'))
    Add-Content -LiteralPath $script:LogPath -Encoding UTF8 -Value "`n===== $(Get-Date -Format o) START $Name ====="
}
function Write-Log([string]$Message, [ValidateSet('INFO','WARN','ERROR')][string]$Level='INFO') {
    $line = '{0} [{1}] {2}' -f (Get-Date -Format o), $Level, $Message
    Write-Host $line
    if ($script:LogPath) { Add-Content -LiteralPath $script:LogPath -Encoding UTF8 -Value $line }
}
function Enter-ValaioliLock {
    $script:UpdateMutex = [System.Threading.Mutex]::new($false, 'Local\ValaioliMediaToolsUpdater')
    try { $script:LockAcquired = $script:UpdateMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $script:LockAcquired = $true }
    if (-not $script:LockAcquired) { Write-Log 'Another updater operation is running; exiting without changes.' 'WARN'; exit 3 }
}
function Exit-ValaioliLock {
    if ($script:LockAcquired -and $script:UpdateMutex) { try { $script:UpdateMutex.ReleaseMutex() } catch {} }
    if ($script:UpdateMutex) { $script:UpdateMutex.Dispose() }
}
function Invoke-TrustedWebRequest([string]$Uri, [string]$OutFile) {
    $u = [uri]$Uri
    if ($u.Scheme -ne 'https') { throw "Refusing non-HTTPS URL: $Uri" }
    Invoke-WebRequest -Uri $u.AbsoluteUri -OutFile $OutFile -TimeoutSec 60 -MaximumRedirection 5 -UserAgent 'Valaioli-DependencyUpdater/1.0' -UseBasicParsing
}
function Invoke-TrustedGet([string]$Uri) {
    $u = [uri]$Uri
    if ($u.Scheme -ne 'https') { throw "Refusing non-HTTPS URL: $Uri" }
    return Invoke-RestMethod -Uri $u.AbsoluteUri -TimeoutSec 45 -Headers @{ 'User-Agent'='Valaioli-DependencyUpdater/1.0'; 'Accept'='application/vnd.github+json' } -MaximumRedirection 5
}
function Compare-ReleaseVersion([string]$Candidate, [string]$Installed) {
    if ([string]::IsNullOrWhiteSpace($Installed) -or $Installed -eq 'unknown') { return 1 }
    try {
        $c = [version]($Candidate -replace '^v','')
        $i = [version]($Installed -replace '^v','')
        return $c.CompareTo($i)
    } catch { return [string]::CompareOrdinal($Candidate, $Installed) }
}
function Get-ActiveToolPath([string]$Tool, [string]$Version, [string]$Executable) {
    if ([string]::IsNullOrWhiteSpace($Version)) { return $null }
    $folder = Get-RootedPath ("tools/versions/{0}/{1}" -f $Tool, $Version)
    $path = Join-Path $folder $Executable
    if (Test-Path -LiteralPath $path) { return $path }
    return $null
}
function Get-ActiveVersion([hashtable]$Manifest, [string]$Tool) {
    $v = $Manifest[$Tool].activeVersion
    if ([string]::IsNullOrWhiteSpace([string]$v)) { return 'unknown' }
    return [string]$v
}
function Set-CheckResult([hashtable]$Manifest, [string]$Tool, [string]$Outcome, $Candidate=$null) {
    $Manifest[$Tool].lastCheckUtc = [DateTime]::UtcNow.ToString('o')
    $Manifest[$Tool].lastOutcome = $Outcome
    $Manifest[$Tool].candidate = $Candidate
    Save-ValaioliManifest $Manifest
}
