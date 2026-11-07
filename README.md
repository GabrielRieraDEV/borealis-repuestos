# Borealis Repuestos — Romero Alfa 1

Sistema de inventario, ventas y caja para PARTES Y ACCESORIO DE MOTO ROMERO ALFA 1, F.P. (Ciudad Bolívar).
Desarrollado por Borealis Software Solutions. Opción contratada: Básica.

**Estado: versión 1.0.0, fases 0 a 6 terminadas.** Falta lo que solo se puede hacer en el local: instalar, probar
la impresora, el lector y Google Drive, y recorrer los 12 criterios con la dueña (`docs/visita/02-pruebas-en-sitio.md`).

## Para la entrega

- `installer\Output\BorealisRepuestos-1.0.0-instalador.exe` — instalador final (se genera con `installer\build.ps1`).
- `docs/guia-rapida.pdf` — guía de una página para imprimir (también en el programa: Ayuda → Guía rápida, F1).
  Se genera con `python installer\make_guide.py`; el contenido se edita ahí.
- `docs/visita/` — **carpeta de la visita para Josner** (Markdown y PDF; `carpeta-de-la-visita.pdf` las junta para imprimir):
  00 el programa en 10 minutos · 01 guía de la visita paso a paso · 02 pruebas en sitio y acta · 03 guion de
  capacitación · 04 problemas y soluciones. Se regeneran con `python installer\make_visit_docs.py`.
- **Modo de prueba:** acceso directo «Borealis Repuestos (modo de prueba)» (`BorealisRepuestos.exe --prueba`): base
  aparte en `C:\ProgramData\BorealisRepuestos-prueba` para las pruebas de la visita y para practicar.
- `docs/revision-final.md` — cada RF, RN y RNF con el archivo y la prueba que lo demuestran.

## Soporte

- **La dueña olvidó su clave:** en la pantalla de entrada, «¿Olvidó la clave de la dueña?» con el código de
  recuperación que anotó en papel (se genera al configurar el sistema o en Usuarios → Código de recuperación).
- **Perdió la clave y el código** (solo Borealis, con acceso a la PC; no viene en el instalador): cerrar el programa,
  copiar `romero.db` a una PC con el entorno de desarrollo y correr
  `python -m repuestos.tools.reset_owner --db romero.db`. Pide la clave nueva, genera un código nuevo y deja constancia
  en la bitácora. Devolver el archivo a `C:\ProgramData\BorealisRepuestos\datos\`.
- **Registro técnico:** `C:\ProgramData\BorealisRepuestos\logs\repuestos.log` (5 archivos de 1 MB).

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

.\.venv\Scripts\python.exe -m pytest -q                  # todo (incluye la prueba de corte de luz, ~15 s)
.\.venv\Scripts\python.exe -m pytest -q -m "not slow"   # sin la prueba de corte de luz
.\.venv\Scripts\ruff.exe check src tests
```

Impresora térmica: Configuración > Impresora de tickets > «Imprimir prueba». Si no hay impresora o no responde, la
venta queda guardada y el programa ofrece reintentar o guardar el ticket en PDF
(`C:\ProgramData\BorealisRepuestos\tickets\`).

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
