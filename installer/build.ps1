# Genera el instalador: pruebas -> PyInstaller (onedir) -> Inno Setup.
# Uso (desde la raíz del repo):  powershell -ExecutionPolicy Bypass -File installer\build.ps1 [-Channel "-preliminar"] [-SkipTests]
param(
    [string]$Channel = "",
    [switch]$SkipTests
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not $SkipTests) {
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Las pruebas fallaron: no se genera el instalador." }
}

$version = & $py -c "import repuestos; print(repuestos.__version__)"
Write-Host "Versión $version"

& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build installer\repuestos.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló." }

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No se encontró Inno Setup 6 (ISCC.exe). Instálelo: winget install JRSoftware.InnoSetup" }

& $iscc "/DAppVersion=$version" "/DChannel=$Channel" installer\repuestos.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falló." }
Get-ChildItem installer\Output\*.exe | Select-Object Name, Length, LastWriteTime
