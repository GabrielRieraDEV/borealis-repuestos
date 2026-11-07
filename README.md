# Borealis Repuestos — Romero Alfa 1

Sistema de inventario, ventas y caja para PARTES Y ACCESORIO DE MOTO ROMERO ALFA 1, F.P. (Ciudad Bolívar).
Desarrollado por Borealis Software Solutions. Opción contratada: Básica.

## Cómo arrancar con Claude Code

1. Crea el repositorio privado `borealis-repuestos` en GitHub y copia esta carpeta tal cual.
2. Abre Claude Code en la raíz. Lee `CLAUDE.md` solo (no hace falta pegarlo).
3. Sigue `docs/04-plan-de-desarrollo.md`: una fase por sesión, pegando el prompt de la fase.
4. Al cerrar cada fase: `pytest -q` en verde, commit, y marcar la fase como hecha en el plan.

## Documentos

- `docs/01-PRD.md` — qué se construye y cómo se acepta.
- `docs/02-reglas-de-negocio.md` — fórmulas de precio, IVA, caja, inventario y fiado.
- `docs/03-modelo-de-datos.md` y `docs/schema.sql` — base de datos.
- `docs/04-plan-de-desarrollo.md` — fases y prompts.

## Requisitos de desarrollo

Python 3.12 (no 3.13+). Para el instalador: Windows con Inno Setup 6.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# datos de desarrollo fuera de C:\ProgramData (la carpeta dev-data/ está en .gitignore)
$env:REPUESTOS_DATA_DIR = "$PWD\dev-data"
.\.venv\Scripts\python.exe -m repuestos

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
```

`REPUESTOS_DATA_DIR` reemplaza la carpeta base `C:\ProgramData\BorealisRepuestos`; dentro se crean `datos\`,
`respaldos\` y `logs\`.

Verificar que las existencias cuadran con los movimientos (RF-44; también corre sola al arrancar):

```powershell
.\.venv\Scripts\python.exe -m repuestos.tools.verify_stock   # código de salida 0 = todo cuadra, 1 = hay diferencias
```

## Generar el instalador

Requisitos: el entorno de desarrollo de arriba e Inno Setup 6 (`winget install JRSoftware.InnoSetup`).

```powershell
powershell -ExecutionPolicy Bypass -File installer\build.ps1                         # versión final
powershell -ExecutionPolicy Bypass -File installer\build.ps1 -Channel "-preliminar"  # instalador preliminar
```

El script corre las pruebas (no genera nada si fallan), arma el programa con PyInstaller en modo onedir
(`installer\repuestos.spec` → `dist\BorealisRepuestos\`) y compila `installer\repuestos.iss` con Inno Setup.
Resultado: `installer\Output\BorealisRepuestos-<versión>[-preliminar]-instalador.exe`. La versión sale de
`src/repuestos/__init__.py`: súbala antes de cada entrega.

Qué hace el instalador:

- Instala el programa en `C:\Program Files\Borealis Repuestos` (pide permisos de administrador; solo Windows 10/11 de 64 bits).
- Crea `C:\ProgramData\BorealisRepuestos\{datos,respaldos,logs}` con permiso de modificación para los usuarios.
- **Nunca borra ni sobrescribe la carpeta de datos**: no copia archivos ahí, y esas carpetas se conservan al
  actualizar y al desinstalar. Al actualizar solo reemplaza los archivos del programa.
- Si el programa está abierto, pide cerrarlo antes de actualizar.

El icono se genera con `python installer\make_icon.py` (ya está en `src/repuestos/ui/repuestos.ico`).

## Tasa BCV

La tasa se descarga de https://www.bcv.org.ve/ al arrancar y cada 2 horas, en segundo plano. El parser está en
`src/repuestos/services/bcv.py`, con instrucciones para actualizarlo si el BCV cambia la página; se prueba con el
HTML real guardado en `tests/fixtures/bcv.html`. La verificación TLS nunca se desactiva: se usa el almacén de
certificados de Windows (`truststore`) porque el sitio del BCV no envía la cadena completa y falla con los
certificados de `certifi`.
