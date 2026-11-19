param([string]$BackupRoot = 'D:\ROSES_AUTO_BACKUPS')

$ErrorActionPreference = 'Stop'
$ddProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ddProperties = Get-Content -LiteralPath (Join-Path $ddProject 'gradle.properties')
$ddVersion = ($ddProperties | Where-Object { $_ -match '^minecraft_version=' }).Split('=')[1].Trim()
$ddTarget = Join-Path $ddProject "dev-workspace\$ddVersion\server"
if (Test-Path -LiteralPath $ddTarget) {
    throw "Test directory already exists. Preserving it: $ddTarget"
}

# Only completed, verified ROSES snapshots can be used. Never run the backup
# script or start.bat from a backup; those launchers can address the live server.
$ddSnapshots = foreach ($ddSlot in 'slot-a', 'slot-b') {
    $ddRoot = Join-Path $BackupRoot $ddSlot
    $ddMarkerPath = Join-Path $ddRoot 'verified.json'
    if (Test-Path -LiteralPath $ddMarkerPath) {
        $ddRecord = Get-Content -LiteralPath $ddMarkerPath -Raw | ConvertFrom-Json
        if ($ddRecord.status -eq 'verified' -and $ddRecord.slot -eq $ddSlot) {
            [pscustomobject]@{Root=$ddRoot; Record=$ddRecord; Time=[datetime]$ddRecord.completedUtc}
        }
    }
}
$ddSnapshot = $ddSnapshots | Sort-Object Time -Descending | Select-Object -First 1
if (-not $ddSnapshot) { throw 'No verified ROSES snapshot is available.' }
$ddSource = [IO.Path]::GetFullPath($ddSnapshot.Root)
$ddBeforeMarker = (Get-FileHash -LiteralPath (Join-Path $ddSource 'verified.json') -Algorithm SHA256).Hash
$ddWorldProperties = Get-Content -LiteralPath (Join-Path $ddSource 'server.properties')
$ddLevelLine = $ddWorldProperties | Where-Object { $_ -match '^level-name=' }
if ($ddLevelLine -and $ddLevelLine -ne 'level-name=world') { throw 'Expected the ROSES world folder to be named world.' }
if (-not (Test-Path -LiteralPath (Join-Path $ddSource 'world\level.dat'))) { throw 'Snapshot world is incomplete.' }
$ddFree = (Get-PSDrive -Name ([IO.Path]::GetPathRoot($ddTarget).TrimEnd(':\'))).Free
if ($ddFree -lt ([long]$ddSnapshot.Record.bytes + 1GB)) { throw 'Not enough space for the test copy.' }

$ddFiles = foreach ($ddFolder in 'world', 'config', 'mods') {
    Get-ChildItem -LiteralPath (Join-Path $ddSource $ddFolder) -Recurse -File -Force | Where-Object {
        $ddRelative = $_.FullName.Substring($ddSource.Length + 1)
        # Old FastBack data is inactive and unnecessary for testing DD.
        $ddRelative -notmatch '(^|\\)(\.git|\.fastback)(\\|$)' -and
        $_.Name -ne 'session.lock' -and
        $_.Name -ne 'desktop.ini' -and
        ($ddFolder -ne 'mods' -or ($_.Extension -eq '.jar' -and $_.Name -notmatch '^(fabric-api-|daily-dress-|fabrictailor-)'))
    }
}
New-Item -ItemType Directory -Path $ddTarget | Out-Null
$ddCopied = @()
foreach ($ddFile in $ddFiles) {
    $ddRelative = $ddFile.FullName.Substring($ddSource.Length + 1)
    $ddDestination = Join-Path $ddTarget $ddRelative
    New-Item -ItemType Directory -Path (Split-Path -Parent $ddDestination) -Force | Out-Null
    Copy-Item -LiteralPath $ddFile.FullName -Destination $ddDestination
    $ddHash = (Get-FileHash -LiteralPath $ddFile.FullName -Algorithm SHA256).Hash
    if ((Get-FileHash -LiteralPath $ddDestination -Algorithm SHA256).Hash -ne $ddHash) {
        throw "Test-copy verification failed: $ddRelative"
    }
    $ddCopied += [ordered]@{path=$ddRelative; sha256=$ddHash; bytes=$ddFile.Length}
}

# Carry the user's already-accepted EULA into the test copy.
Copy-Item -LiteralPath (Join-Path $ddSource 'eula.txt') -Destination (Join-Path $ddTarget 'eula.txt')
# Keep gameplay settings while replacing all network, management, and external
# service settings with test-local values. No live RCON secrets are copied.
$ddGameplayKeys = 'difficulty','gamemode','generator-settings','level-type','max-players',
    'simulation-distance','spawn-protection','sync-chunk-writes','use-native-transport',
    'view-distance','enable-command-block','hardcore','allow-flight','pvp'
$ddSafeProperties = $ddWorldProperties | Where-Object { $_.Split('=')[0] -in $ddGameplayKeys }
$ddSafeProperties += @('level-name=world','server-ip=127.0.0.1','server-port=25566',
    'online-mode=false','enable-rcon=false','enable-query=false','management-server-enabled=false',
    'white-list=false','motd=Daily Dress - ROSES 26.3 test copy','pause-when-empty-seconds=-1')
$ddSafeProperties | Set-Content -LiteralPath (Join-Path $ddTarget 'server.properties') -Encoding ASCII
$ddAfterMarker = (Get-FileHash -LiteralPath (Join-Path $ddSource 'verified.json') -Algorithm SHA256).Hash
if ($ddBeforeMarker -ne $ddAfterMarker) { throw 'Backup changed during the copy. Do not use this test directory.' }
$ddProvenance = [ordered]@{
    source=$ddSource; snapshotCompletedUtc=$ddSnapshot.Record.completedUtc
    minecraft=$ddVersion; copiedFiles=$ddCopied.Count; files=$ddCopied
    notes='Independent test copy; Fabric API, Fabric Tailor, and DD are supplied by Gradle. Offline UUIDs differ from live ROSES.'
}
$ddProvenance | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $ddTarget 'DD-TEST-SOURCE.json') -Encoding UTF8
Write-Host "Verified $($ddCopied.Count) copied files from $ddSource"
Write-Host "DD test server: $ddTarget"
Write-Host 'Start with Run Daily Dress Test Server.bat and connect to localhost:25566.'
