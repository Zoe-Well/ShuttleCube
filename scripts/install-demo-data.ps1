param(
    [string]$SourceDatabase = "backend\.demo-seed-validation.db",
    [string]$DesktopDataDirectory = ".desktop-dev-data"
)

$ErrorActionPreference = "Stop"

$workspace = (Resolve-Path -LiteralPath ".").Path
$dataRoot = (Resolve-Path -LiteralPath $DesktopDataDirectory).Path
$databaseDirectory = (Resolve-Path -LiteralPath (Join-Path $dataRoot "database")).Path
$attachmentsDirectory = (Resolve-Path -LiteralPath (Join-Path $dataRoot "attachments")).Path
$source = (Resolve-Path -LiteralPath $SourceDatabase).Path
$target = Join-Path $databaseDirectory "shuttlecube.db"

foreach ($path in @($dataRoot, $databaseDirectory, $attachmentsDirectory, $source, $target)) {
    if (-not $path.StartsWith($workspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the workspace: $path"
    }
}

if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    throw "Desktop database does not exist: $target"
}

$running = Get-Process | Where-Object {
    $_.ProcessName -match "shuttlecube-desktop" -or
    ($_.ProcessName -eq "python" -and $_.Path -like "*ShuttleCube*")
}
if ($running) {
    throw "ShuttleCube is still running. Close the desktop app before installing demo data."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $dataRoot ("backups\Before-Demo-Data-" + $timestamp)
$backupDatabaseDirectory = Join-Path $backupRoot "database"
$backupAttachmentsDirectory = Join-Path $backupRoot "attachments"
New-Item -ItemType Directory -Path $backupDatabaseDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $backupAttachmentsDirectory -Force | Out-Null

Copy-Item -LiteralPath $target -Destination (Join-Path $backupDatabaseDirectory "shuttlecube.db")
Get-ChildItem -LiteralPath $attachmentsDirectory -Force | Copy-Item -Destination $backupAttachmentsDirectory -Recurse

foreach ($sidecarName in @("shuttlecube.db-wal", "shuttlecube.db-shm")) {
    $sidecar = Join-Path $databaseDirectory $sidecarName
    if (Test-Path -LiteralPath $sidecar) {
        Copy-Item -LiteralPath $sidecar -Destination (Join-Path $backupDatabaseDirectory $sidecarName)
        Remove-Item -LiteralPath $sidecar -Force
    }
}

Copy-Item -LiteralPath $source -Destination $target -Force
Get-ChildItem -LiteralPath $attachmentsDirectory -Force | Remove-Item -Recurse -Force

[PSCustomObject]@{
    Backup = $backupRoot
    Database = $target
}
