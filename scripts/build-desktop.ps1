param(
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $projectRoot "frontend"
$backend = Join-Path $projectRoot "backend"
$desktopSpec = Join-Path $projectRoot "desktop\ShuttleCube.spec"
$desktopDist = Join-Path $projectRoot "dist\desktop"
$desktopWork = Join-Path $projectRoot "build\desktop"
$env:UV_CACHE_DIR = Join-Path $projectRoot ".cache\uv"

# pnpm can preserve the original workspace drive in its metadata. Building from
# that same drive avoids Vite treating index.html as a cross-drive absolute path.
$modulesMetadata = Join-Path $projectRoot "node_modules\.modules.yaml"
if (Test-Path $modulesMetadata) {
    $virtualStore = Select-String -Path $modulesMetadata -Pattern '^virtualStoreDir:\s*(.+)$' | Select-Object -First 1
    if ($virtualStore) {
        $detectedRoot = Split-Path -Parent (Split-Path -Parent $virtualStore.Matches[0].Groups[1].Value.Trim())
        if (Test-Path (Join-Path $detectedRoot "frontend\package.json")) {
            $frontend = Join-Path $detectedRoot "frontend"
        }
    }
}

Push-Location $frontend
try {
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
} finally {
    Pop-Location
}

uv sync --project $backend --extra desktop
if ($LASTEXITCODE -ne 0) { throw "Desktop dependency sync failed." }
& (Join-Path $backend ".venv\Scripts\pyinstaller.exe") --noconfirm --clean --distpath $desktopDist --workpath $desktopWork $desktopSpec
if ($LASTEXITCODE -ne 0) { throw "Desktop executable build failed." }

$executable = Join-Path $desktopDist "ShuttleCube\ShuttleCube.exe"
if (-not (Test-Path $executable)) { throw "Desktop executable was not produced." }

$smokeParent = Join-Path $projectRoot ".test-tmp"
$smokeData = Join-Path $smokeParent ("desktop-smoke-" + [guid]::NewGuid().ToString("N"))
$previousDataDir = $env:SHUTTLECUBE_DATA_DIR
$previousSmokeTest = $env:SHUTTLECUBE_DESKTOP_SMOKE_TEST
New-Item -ItemType Directory -Path $smokeData -Force | Out-Null
try {
    $env:SHUTTLECUBE_DATA_DIR = $smokeData
    $env:SHUTTLECUBE_DESKTOP_SMOKE_TEST = "true"
    $smokeProcess = Start-Process -FilePath $executable -Wait -PassThru -WindowStyle Hidden
    if ($smokeProcess.ExitCode -ne 0) { throw "Desktop startup smoke test failed." }
    if (-not (Test-Path (Join-Path $smokeData "database\shuttlecube.db"))) {
        throw "Desktop startup smoke test did not create its database."
    }
} finally {
    $env:SHUTTLECUBE_DATA_DIR = $previousDataDir
    $env:SHUTTLECUBE_DESKTOP_SMOKE_TEST = $previousSmokeTest
    $resolvedParent = [System.IO.Path]::GetFullPath($smokeParent).TrimEnd('\') + '\'
    $resolvedSmoke = [System.IO.Path]::GetFullPath($smokeData)
    if ($resolvedSmoke.StartsWith($resolvedParent, [System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedSmoke)) {
        Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force
    }
}

if ($Installer) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $knownIscc = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
        if ($knownIscc) { $iscc = Get-Item $knownIscc }
    }
    if (-not $iscc) {
        throw "Inno Setup 6 is required to build the installer."
    }
    $isccPath = if ($iscc.Source) { $iscc.Source } else { $iscc.FullName }
    & $isccPath (Join-Path $projectRoot "desktop\installer\ShuttleCube.iss")
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
}

Write-Host "Desktop build created at: $executable"
