# CLAUDE.md — Borealis Repuestos (Romero Alfa 1)

Instrucciones permanentes para Claude Code. Léelas completas al inicio de cada sesión.

## Qué es este proyecto

Sistema de escritorio de **inventario, ventas y caja** para una tienda de repuestos de moto en Ciudad Bolívar, Venezuela
(PARTES Y ACCESORIO DE MOTO ROMERO ALFA 1, F.P.). Lo construye Borealis Software Solutions. Opción contratada: **Básica**.

La clienta quiere, por encima de todo, que **el inventario baje solo con cada venta**, saber cuánto le queda para volver
a pedir, y ver cada mes cuánto tiene invertido, cuánto compró, cuánto vendió y cuánto le quedó. Un sistema anterior
"cargaba el inventario pero nunca restaba" y otro dejó de funcionar por licencia: **la confiabilidad es el producto**.

Documentos fuente (léelos antes de tocar un módulo; si el código y los documentos chocan, mandan los documentos y me avisas):

| Archivo | Contenido |
|---|---|
| `docs/01-PRD.md` | Alcance, requisitos funcionales (RF-xx) y criterios de aceptación |
| `docs/02-reglas-de-negocio.md` | Reglas RN-xx con fórmulas y ejemplos numéricos |
| `docs/03-modelo-de-datos.md` + `docs/schema.sql` | Tablas, escalas de enteros, invariantes |
| `docs/04-plan-de-desarrollo.md` | Fases, entregables y definición de terminado |

## Stack (decisiones cerradas, no cambiar sin preguntar)

- **Python 3.12**, **PySide6** (no PyQt6: licencia LGPL para software propietario), **SQLite** en modo WAL.
- **Sin ORM.** Repositorios con SQL escrito a mano y parámetros `?`. Nunca concatenar SQL con datos.
- `python-escpos` para la impresora térmica de 80 mm; `reportlab` para reportes en PDF.
- `pytest` para pruebas. `PyInstaller` (modo onedir) + **Inno Setup** para el instalador de Windows.
- Todo funciona **sin internet**. Internet solo se usa para descargar la tasa BCV; si falla, se carga a mano.

## Estructura

```
src/repuestos/
  app.py                 # arranque, migraciones, login
  config.py              # rutas, carga de settings
  domain/                # reglas puras, sin Qt ni SQL (money.py, pricing.py, inventory.py, cash.py, credit.py)
  db/                    # connection.py, migrations/, repositories/ (un archivo por agregado)
  services/              # casos de uso transaccionales (sale_service.py, purchase_service.py, ...)
  ui/                    # ventanas y widgets PySide6; nunca SQL aquí
  printing/              # ticket ESC/POS y PDF
  backup/                # respaldo local + carpeta en la nube
tests/                   # espejo de src/; domain y services con cobertura alta
docs/
```

Capas: `ui` → `services` → (`domain` + `db/repositories`). `domain` no importa nada de `db` ni de `ui`.

## Dinero, cantidades y redondeo (crítico)

- **Nunca `float`** para dinero, tasas, cantidades ni porcentajes. En Python: `decimal.Decimal`. En SQLite: enteros escalados.
- Escalas en la base de datos (sufijo en el nombre de la columna):

| Sufijo | Qué guarda | Escala | Ejemplo |
|---|---|---|---|
| `_e4` | Precio o costo **unitario** en USD | ×10.000 | 12,5000 USD → `125000` |
| `_e2` | Montos y totales (USD o Bs) | ×100 | 1.234,56 Bs → `123456` |
| `_e3` | Cantidades | ×1.000 | 2,5 m → `2500` |
| `_e6` | Tasa de cambio Bs/USD | ×1.000.000 | 231,046800 → `231046800` |
| `_bp` | Porcentajes | ×100 | 16 % → `1600` |

- La conversión entero ↔ `Decimal` ocurre **solo** en `db/repositories`. Servicios y dominio trabajan con `Decimal`.
- Redondeo: **siempre explícito**. `ROUND_HALF_UP` para montos; techo al múltiplo solo donde RN-03 lo pide (precio unitario en Bs).
  El redondeo por defecto de Python (`ROUND_HALF_EVEN`) contradice la especificación: no lo uses nunca por omisión.
- Toda la aritmética monetaria vive en `domain/money.py` y `domain/pricing.py`, con pruebas para cada fórmula de `docs/02`.

## Integridad de datos (crítico)

- Cada venta, compra, ajuste, abono y cierre es **una sola transacción** (`BEGIN IMMEDIATE` … `COMMIT`). Si algo falla, nada queda a medias.
- Conexión: `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000`.
  `synchronous=FULL` es a propósito: en el local se va la luz.
- **Invariante de inventario:** `products.stock_e3` = suma de `inventory_movements.qty_e3` del producto. Cada cambio de
  existencia escribe un movimiento en la misma transacción. Hay una prueba que lo verifica y un comando de verificación.
- **No se borran filas** de ventas, compras, movimientos, pagos ni bitácora. Se anulan (`status='VOIDED'`) con usuario,
  fecha y motivo. Productos y clientes se desactivan (`active=0`).
- Toda acción sensible (anular, ajustar inventario, cambiar precio o costo, cambiar tasa a mano, abrir o cerrar caja,
  iniciar sesión) escribe en `audit_log`.
- Migraciones numeradas en `db/migrations/NNNN_descripcion.sql`, aplicadas al arrancar y registradas en `schema_migrations`.
  La `0001` es `docs/schema.sql`. Nunca editar una migración ya publicada: crear una nueva.

## Interfaz

- Todo texto visible en **español de Venezuela**, claro y sin tecnicismos. La dueña no es técnica.
- Montos en pantalla: `Bs 1.234,56` y `USD 12,50` (punto de miles, coma decimal). Fechas `dd/mm/aaaa`.
- La venta se hace **con teclado**: buscar (F2), cantidad, Enter agrega, F9 cobrar, Esc cancelar. El lector de código de barras
  escribe como teclado y termina en Enter: escanear agrega el producto directo.
- El vendedor nunca ve costos ni ganancias. Ocultarlo en la UI **y** negarlo en el servicio (`PermissionError`).
- Mensajes de error que digan qué hacer ("No hay tasa del día. Cárguela en Tasa BCV"), nunca trazas.

## Código

- Código, nombres de tablas y columnas en **inglés**; textos de UI y documentos en español. Usa el glosario.
- Type hints en todo. Funciones de dominio puras y probadas. Nada de lógica de negocio en widgets.
- Antes de dar algo por terminado: `pytest` en verde, `ruff check` limpio, y probar el flujo a mano si toca UI.
- Comandos: `python -m repuestos` (ejecutar), `pytest -q`, `ruff check src tests`, `python -m repuestos.tools.verify_stock`.

## Glosario ES → EN

| Español | Código |
|---|---|
| Producto / repuesto | `product` |
| Existencia | `stock` |
| Mínimo (alerta) | `min_stock` |
| Movimiento de inventario | `inventory_movement` |
| Ajuste (daño, faltante, uso interno, conteo) | `adjustment` (`DAMAGE`, `MISSING`, `INTERNAL_USE`, `COUNT`) |
| Compra / proveedor | `purchase` / `supplier` |
| Venta / renglón | `sale` / `sale_item` |
| Nota de entrega | `delivery_note` (doc_type `NE`) |
| Tasa BCV | `exchange_rate` |
| Caja (sesión de caja) | `cash_session` |
| Fiado / cuenta por cobrar | `receivable` |
| Abono | `credit_payment` |
| Vuelto | `change` (pago con `is_change=1`) |
| Dueña / vendedor | `owner` / `seller` |
| Bitácora | `audit_log` |
| Cierre mensual (foto del inventario) | `monthly_snapshot` |

## Lo que NO está en esta fase (no lo construyas aunque parezca fácil)

Facturación fiscal, consulta desde el celular, precios por margen, compras en USDT con su tasa, deudas con proveedores,
kits, cotizaciones, apartados, devoluciones con nota de crédito, fotos, etiquetas, segunda sucursal. Ver `docs/01-PRD.md` §3.
El modelo de datos deja **preparados** algunos campos para la facturación fiscal; no les pongas lógica.

## Reutilización

Si tienes acceso al repositorio `borealis-minimarket`, reutiliza (copiando y adaptando, sin dependencia cruzada)
`money`, la capa de conexión SQLite, el patrón de repositorios, la impresión ESC/POS y el empaquetado. Las reglas de este
proyecto mandan sobre las del minimarket cuando difieran.
