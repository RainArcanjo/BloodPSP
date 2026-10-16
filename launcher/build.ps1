param(
    [string]$Python,
    [string]$BuildRoot,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist'),
    [string]$EnvironmentDirectory
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
if (-not $BuildRoot) {
    $BuildRoot = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'Build\launcher'
}
if (-not $Python) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*\WindowsApps\*') {
        $Python = $pythonCommand.Source
    } elseif (Test-Path -LiteralPath 'C:\Python314\python.exe') {
        $Python = 'C:\Python314\python.exe'
    } else {
        throw 'Specify Python 3.10-3.15: build.ps1 -Python C:\path\python.exe'
    }
}
if (-not $EnvironmentDirectory) { $EnvironmentDirectory = Join-Path $BuildRoot 'venv' }
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $EnvironmentDirectory 'Scripts\python.exe'))) {
    & $Python -m venv $EnvironmentDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
$buildPython = Join-Path $EnvironmentDirectory 'Scripts\python.exe'
& $buildPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install launcher dependencies.' }
Push-Location $PSScriptRoot
try {
    & $buildPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Launcher tests failed.' }
    & $buildPython make_icon.py (Join-Path $PSScriptRoot 'resources\app.ico')
    if ($LASTEXITCODE -ne 0) { throw 'Could not generate icon.' }
    & $buildPython -c "import pathlib,shutil,sys; shutil.copy2(pathlib.Path(sys.base_prefix)/'LICENSE.txt',pathlib.Path('resources/licenses/Python-LICENSE.txt'))"
    if ($LASTEXITCODE -ne 0) { throw 'Could not include Python license.' }
    & $buildPython -m PyInstaller --noconfirm --clean --distpath $OutputDirectory --workpath (Join-Path $BuildRoot 'pyinstaller') BloodPSPLauncher.spec
    if ($LASTEXITCODE -ne 0) { throw 'Could not package executable.' }
    $package = Join-Path $OutputDirectory 'BloodPSPLauncher'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination (Join-Path $package 'README.md')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LICENSE') -Destination (Join-Path $package 'LICENSE.txt')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD-PARTY-NOTICES.md') -Destination $package
    Write-Output (Join-Path $package 'BloodPSPLauncher.exe')
} finally {
    Pop-Location
}
