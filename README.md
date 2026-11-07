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
