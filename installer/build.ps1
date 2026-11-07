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

# Paquete de entrega para la visita (instalador + documentos + LÉEME), solo en la versión final
if (-not $Channel) {
    & $py installer\make_guide.py | Out-Null
    & $py installer\make_visit_docs.py | Out-Null
    $pkg = "installer\Output\Visita-Romero-Alfa-1-v$version"
    Remove-Item -Recurse -Force $pkg -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force "$pkg\visita" | Out-Null
    Copy-Item "installer\Output\BorealisRepuestos-$version-instalador.exe" $pkg
    Copy-Item "docs\guia-rapida.pdf", "docs\visita\carpeta-de-la-visita.pdf" $pkg
    Copy-Item "docs\visita\0*.pdf" "$pkg\visita"
    Copy-Item "installer\LEEME-visita.txt" "$pkg\LEEME.txt"
    Compress-Archive -Path "$pkg\*" -DestinationPath "$pkg.zip" -Force
    Get-Item "$pkg.zip" | Select-Object Name, Length
}
