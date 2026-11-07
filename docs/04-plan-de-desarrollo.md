# Plan de desarrollo y prompts para Claude Code

Contrato: **4 días hábiles** de desarrollo + visita de instalación y capacitación. El plazo es corto: cada fase tiene un
entregable que se puede probar y una lista de lo que **no** hay que hacer. Una fase por sesión de Claude Code.

| Fase | Cuándo | Entregable | Hito de pago |
|---|---|---|---|
| ☑ 0 · Base | Día 1, mañana | Proyecto, base de datos, reglas de dinero con pruebas, login | — |
| ☑ 1 · Productos y tasa | Día 1, tarde | Catálogo, búsqueda, tasa BCV, **instalador preliminar** | Se instala en el local para que la dueña empiece a cargar productos |
| ☑ 2 · Compras e inventario | Día 2 | Compras con costo promedio, ajustes, conteo, para pedir | — |
| ☑ 3 · Caja y ventas | Día 3 | Venta, cobro mixto, vuelto, nota de entrega, cierre ciego | **Hito 2 (25 %)** |
| ☐ 4 · Fiado | Día 4, mañana | Clientes, venta a fiado, abonos, estado de cuenta | — |
| ☐ 5 · Reportes y respaldo | Día 4, tarde | Reportes, resumen del mes, respaldo local y en la nube | — |
| ☐ 6 · Entrega | Visita | Instalador final, pruebas en sitio, guía rápida, capacitación | **Hito 3 (25 %)** |

**Regla de oro del plazo:** si una fase se atrasa, se recorta lo marcado **d** en el PRD, nunca una regla de dinero ni una
prueba de invariante.

---

## Cómo trabajar cada sesión

1. Abre Claude Code en la raíz del repo (lee `CLAUDE.md` solo).
2. Pega el prompt de la fase.
3. Revisa el plan que propone antes de que escriba código. Corrige si se sale del alcance.
4. Al terminar: `pytest -q` y `ruff check src tests` en verde, prueba manual del entregable, commit con el mensaje
   `fase N: <resumen>` y marca la casilla de arriba.

### Prompt de arranque (solo la primera vez, antes de la Fase 0)

```
Lee CLAUDE.md y todos los archivos de docs/ completos, incluido docs/schema.sql.
No escribas código todavía. Quiero:
1. Un resumen de 10 líneas de lo que vamos a construir y lo que NO.
2. Una lista de contradicciones, huecos o ambigüedades entre PRD, reglas, modelo de datos y CLAUDE.md, con tu
   propuesta para cada una.
3. Riesgos técnicos que veas para entregar en 4 días (impresión, tasa BCV, empaquetado, Windows).
Espera mi respuesta antes de empezar la Fase 0.
```

### Prompt de revisión (al final de cualquier fase)

```
Revisa lo hecho en esta fase contra docs/01-PRD.md y docs/02-reglas-de-negocio.md.
Para cada RF y RN que toca la fase, dime: cumplido / parcial / falta, con el archivo y la prueba que lo demuestra.
Busca en particular: floats en dinero, redondeos sin modo explícito, escrituras fuera de transacción, SQL en la UI,
costos visibles para el vendedor. Arregla lo que encuentres y vuelve a correr las pruebas.
```

---

## Fase 0 · Base

```
Fase 0 del plan (docs/04-plan-de-desarrollo.md). Lee CLAUDE.md y docs/03-modelo-de-datos.md.

Construye:
1. pyproject.toml (Python 3.12) con dependencias: PySide6, python-escpos, reportlab, httpx; dev: pytest, ruff,
   pyinstaller. Paquete en src/repuestos con la estructura de CLAUDE.md. Punto de entrada `python -m repuestos`.
2. db/connection.py: abre C:\ProgramData\BorealisRepuestos\datos\romero.db (en desarrollo, una ruta configurable por
   variable de entorno REPUESTOS_DATA_DIR) con los PRAGMA de CLAUDE.md. Context manager `transaction()` que usa
   BEGIN IMMEDIATE y hace rollback ante cualquier excepción.
3. db/migrations: runner que aplica en orden los NNNN_*.sql pendientes, cada uno en su transacción, y registra la versión
   en schema_migrations. 0001 = copia exacta de docs/schema.sql.
4. domain/money.py: helpers to_db/from_db por escala (_e2, _e3, _e4, _e6, _bp) que fallan si sobran decimales;
   funciones HU(x, n) (ROUND_HALF_UP) y TECHO(x, m) (múltiplo hacia arriba).
5. domain/pricing.py: precio_bs (RN-03), renglón (RN-04), totales base/IVA (RN-05), equivalente y vuelto (RN-06),
   deuda y abono en USD (RN-07), costo promedio (RN-08) y compra por empaque. Funciones puras con Decimal.
6. tests/test_pricing.py: TODOS los ejemplos numéricos de docs/02 y los criterios 2 a 6 del PRD §7, uno por prueba,
   con los valores exactos del documento.
7. Seguridad: hash y verificación de contraseñas con hashlib.scrypt; bloqueo de 5 minutos tras 5 intentos (RF-01).
8. UI mínima: ventana de login y asistente de primer arranque (RF-02) que crea la dueña y guarda los datos del negocio
   en settings; ventana principal vacía con la barra de estado (usuario, tasa: "sin tasa", caja: "cerrada",
   respaldo: "nunca"). Servicio de auditoría `audit(action, entity, entity_id, details, authorized_by=None)`.
9. Logging rotativo (RNF-07).

No hagas todavía: productos, ventas, impresión ni empaquetado.
Termina con pytest y ruff en verde y un resumen de lo hecho y lo pendiente.
```

**Terminado cuando:** las pruebas de `test_pricing.py` reproducen cada número de `docs/02` y del PRD §7; se puede crear
la dueña e iniciar sesión.

---

## Fase 1 · Productos, tasa e instalador preliminar

```
Fase 1. Lee docs/01-PRD.md §4.1–4.3 (RF-03 a RF-22) y RN-01, RN-02, RN-09, RN-10.

Construye:
1. Repositorio y servicio de productos: alta con código R-00001 desde doc_sequences, edición, desactivación,
   existencia inicial con movimiento INITIAL (RN-08 último punto), search_text normalizado (minúsculas, sin acentos).
   Cambios de precio y costo solo para owner y con auditoría antes/después.
2. Búsqueda multi-palabra (RF-12): cada palabra debe aparecer en search_text (AND), cualquier orden; código de barras
   exacto tiene prioridad. Prueba de rendimiento con 5.000 productos generados: < 300 ms.
3. Pantalla de productos: lista con búsqueda en vivo y ficha. Carga rápida (RF-11): Ctrl+Enter guarda y abre otra ficha
   conservando categoría, marca y estante; el foco vuelve al nombre. Para el vendedor, sin campos de costo ni precio editable.
4. Categorías editables (RF-14). Pantalla de configuración (RF-06). Usuarios: la dueña crea, desactiva y
   restablece vendedores (RF-03).
   Diálogo reutilizable "Autorizar con clave de la dueña" (RF-04) que devuelve el id de la dueña o None.
5. Tasa BCV (RF-20 a RF-22, RN-01): módulo services/bcv.py con httpx (timeout 10 s, verificación TLS activada).
   El parser va aislado y se prueba con un HTML guardado en tests/fixtures/bcv.html; históricamente el USD está en el
   bloque con id "dolar" y la fecha valor en un span con atributo content; confírmalo con el HTML real y documenta en el
   código cómo actualizarlo si el BCV cambia la página. Hilo de fondo (QThread) cada 2 horas, nunca bloquea la UI.
   Carga manual para la dueña. Barra de estado con tasa, fecha valor, origen y aviso si tiene > 3 días.
6. tools/verify_stock.py (RF-44) y su ejecución al arrancar.
7. Empaquetado preliminar: spec de PyInstaller (onedir, sin consola, icono) y script Inno Setup en installer/ que instala
   en Program Files, crea C:\ProgramData\BorealisRepuestos\{datos,respaldos,logs} con permiso users-modify y NUNCA borra
   ni sobrescribe la carpeta de datos al actualizar o desinstalar. Documenta en README cómo generar el instalador.

Pruebas: alta con existencia inicial deja stock = movimientos; búsqueda "pastilla bera 150" encuentra el producto de
ejemplo del PRD; vendedor no puede cambiar precio (PermissionError en el servicio); parser BCV con el fixture;
tasa vigente con fechas valor futuras y pasadas (RN-01).

No hagas: compras, ventas, fotos, importación desde Excel, precios por margen.
```

**Terminado cuando:** el instalador preliminar corre en una Windows 10/11 limpia, se cargan 20 productos de prueba en
menos de 10 minutos y la búsqueda los encuentra. **Antes de instalar en el local, confirmar la versión de Windows (PRD P1).**

---

## Fase 2 · Compras e inventario

```
Fase 2. Lee PRD §4.4 y §4.5 (RF-30 a RF-44) y RN-08, RN-09, RN-10, RN-14 (compras y ajustes).

Construye:
1. Proveedores (crear rápido desde la compra).
2. Registro de compra (RF-30) con renglones, ayuda de compra por empaque y total. Al guardar, en UNA transacción:
   purchase, items, movimientos PURCHASE, existencia y costo promedio (RN-08, en el orden de los renglones; si el mismo
   producto aparece dos veces, se aplica dos veces).
3. Anulación de compra (RF-31): PURCHASE_VOID por renglón, motivo obligatorio, bloqueo si deja existencias negativas,
   sin recalcular costo.
4. Ajustes (RF-41) y conteo físico (RF-42) con los tipos de RN-09; cada movimiento guarda unit_cost_usd_e4 del momento.
5. Kardex e historial de compras en la ficha del producto (RF-16).
6. Lista "Para pedir" (RF-43, RN-10) con proveedor y costo de la última compra; contador en la pantalla principal.
   La impresión en PDF puede esperar a la Fase 5; deja la consulta lista.

Pruebas: criterio 2 del PRD (10,60 USD); compra por empaque (24 u a 1,5000); compra con existencia previa negativa o
cero toma el costo de compra; anulación de compra; conteo con diferencia positiva y negativa; invariante de existencias
después de cada operación; ningún float.

No hagas: deudas con proveedores, compras en USDT, vencimientos.
```

**Terminado cuando:** se registran compras y ajustes de prueba y `verify_stock` no reporta diferencias.

---

## Fase 3 · Caja y ventas (Hito 2)

```
Fase 3. Lee PRD §4.6 y §4.7 (RF-50 a RF-63) y RN-03 a RN-06, RN-09, RN-11, RN-12, RN-14.

Construye:
1. Caja: apertura (RF-60), entradas y salidas (RF-61), cierre ciego (RF-62) con esperado por moneda según RN-11,
   historial (RF-63). Una sola sesión abierta. El vendedor no ve esperado ni diferencia.
2. Pantalla de venta solo con teclado (RF-50): F2 buscar, lector de código de barras (entrada que termina en Enter
   agrega el producto), cantidad con decimales si el producto lo permite, Supr quita, F9 cobra, Esc cancela.
   Muestra precio en Bs (RN-03), total, referencia USD y tasa. Bloquea si no hay caja abierta o no hay tasa.
3. Cliente (RF-51): Consumidor final por defecto; buscar o crear por cédula/RIF.
4. Cobro (RF-52, RN-06): pagos mixtos, falta en Bs y USD, vuelto en USD/Bs con el resto calculado. La opción "Fiado"
   aparece pero queda deshabilitada hasta la Fase 4. USDT solo si payment_usdt_enabled = 1.
5. services/sale_service.py: cobrar en UNA transacción (ver la tabla de transacciones en docs/03): correlativo NE,
   sale, items con copias de precio y costo promedio, pagos y vuelto, movimientos SALE, existencias.
   Existencia insuficiente: bloquea salvo allow_negative_stock o autorización de la dueña (RN-09).
6. Anulación (RF-53, RN-14) solo con la sesión de la venta abierta; vendedor con autorización.
7. Impresión (RF-54, RN-12): printing/ticket.py con python-escpos (impresora Windows por nombre) que arma la nota de
   entrega de 80 mm (48 columnas). Implementación alternativa que guarda un PDF/texto para desarrollo y para cuando la
   impresora falla. La venta nunca se revierte por un error de impresión. Reimpresión desde la lista de ventas (RF-56).
8. Ticket de cierre de caja.

Pruebas: criterios 1, 3, 4 y 5 del PRD §7 de punta a punta contra la base (servicio, no UI); invariantes 2, 3, 6, 7 y 8
de docs/03; anulación devuelve existencias; vuelto que excede lo debido se rechaza; correlativos sin huecos aunque una
venta falle a mitad (rollback).
Prueba de corte de luz (RNF-03): un script que lanza un subproceso que cobra ventas en bucle y lo mata con kill a los
N ms; luego integrity_check = ok, verify_stock sin diferencias e invariante 3 en todas las ventas. Repetir 20 veces.

No hagas: fiado (Fase 4), devoluciones, descuentos, cotizaciones, apartados, facturación fiscal.
```

**Terminado cuando:** se vende con teclado y lector, la nota sale por la térmica (o PDF), la caja cuadra con el criterio 5
y la prueba de corte de luz pasa 20 de 20. **Aquí se cobra el Hito 2.**

---

## Fase 4 · Fiado

```
Fase 4. Lee PRD §4.8 (RF-70 a RF-73) y RN-07, RN-14 (abonos).

Construye:
1. Clientes: habilitar fiado, límite en USD y plazo (RF-70). Consumidor final nunca.
2. Venta a fiado total o parcial (RF-71): la opción Fiado del cobro guarda credit_ves_e2 y credit_usd_e2 en la venta
   y crea el receivable con vencimiento. Control de límite con autorización de la dueña.
3. Abonos (RF-72): cualquier forma de pago menos fiado, con la tasa vigente; reparto FIFO en credit_allocations;
   pagos en la caja abierta; comprobante AB-000001 impreso. Anulación de abono con su sesión abierta.
4. Estado de cuenta por cliente y lista de deudores con vencidas resaltadas y total por cobrar (RF-73).
5. Anular una venta con fiado: anula la deuda si no tiene abonos; si los tiene, se bloquea (RN-07).

Pruebas: criterio 6 del PRD (12,51 USD; abono Bs 1.200 a 240,00 = 5,00 USD; saldo 7,51); FIFO con dos deudas;
abono mayor que el saldo rechazado; límite; invariantes 3, 4 y 5; el efectivo de los abonos entra al arqueo (RN-11).
```

**Terminado cuando:** el criterio 6 pasa en la UI y en las pruebas.

---

## Fase 5 · Reportes y respaldo

```
Fase 5. Lee PRD §4.9 y §4.10 (RF-80 a RF-92) y RN-13, RN-15, RN-16.

Construye:
1. Reportes en PDF con reportlab (encabezado con datos del negocio, fecha de emisión, paginado):
   ventas del día (RF-80, el vendedor solo las suyas y sin costos), monto vendido por período (RF-81),
   resumen del mes con tabla de 12 meses (RF-82, RN-13), inventario valorizado con productos sin costo (RF-83),
   para pedir (RF-84). Vista previa en pantalla antes de imprimir.
2. Foto mensual (RN-13) en el primer arranque de cada mes.
3. Respaldo (RF-90, RN-15): backup API + integrity_check, 30 locales + 30 en la carpeta de nube, disparado al arrancar
   (> 12 h), al cerrar caja y al salir, en segundo plano sin congelar la UI. Estado en la barra.
4. Restaurar (RF-91) con doble confirmación y copia previa.
5. (d) RF-92: al cerrar caja y al salir, escribir "Inventario de hoy.pdf" y "Resumen del mes.pdf" en la carpeta de nube.
6. Visor de bitácora con filtros (RF-05).

Pruebas: el caso del resumen del mes de abajo da exactamente esos números; el vendedor no puede generar reportes de
costos (servicio); respaldo verificado y restauración de ida y vuelta conserva todos los conteos de filas.
```

### Caso de prueba del resumen del mes (criterio 8 del PRD)

Mes de prueba: noviembre de 2026, sin foto del mes anterior. Tasa 231,0468, múltiplo 5,00.

| # | Operación |
|---|---|
| 1 | Producto A "Pastillas de freno Bera 150", precio 15,00 USD, existencia inicial 10 a 10,00 USD |
| 2 | Producto B "Cable eléctrico" por metro con fracción, precio 0,80 USD, existencia inicial 100 m a 0,30 USD |
| 3 | Compra: 5 A a 13,00 USD → costo A = 11,0000 |
| 4 | Venta 1: 3 A (Bs 3.470,00 c/u) + 2,5 m B (Bs 185,00) → Bs 10.872,50; ref 47,00 USD |
| 5 | Ajuste: 2 m de B dañados |
| 6 | Venta 2: 1 A, anulada en la misma caja |

| Línea del resumen | Valor esperado |
|---|---|
| Inversión al cierre del mes anterior | sin dato |
| Inversión hoy | 160,65 USD (A: 12 × 11,00 = 132,00; B: 95,5 × 0,30 = 28,65) |
| Compras del mes | 65,00 USD |
| Ventas con IVA | 47,00 USD / Bs 10.872,50 |
| IVA | 6,48 USD / Bs 1.499,66 |
| Ventas netas | 40,52 USD (Bs 9.372,84) |
| Costo de lo vendido | 33,75 USD (A: 3 × 11,00; B: 2,5 × 0,30) |
| Ganancia bruta | 6,77 USD |
| Pérdidas | 0,60 USD |
| Por cobrar | 0,00 USD |
| Resultado antes de gastos | 6,17 USD |

**Terminado cuando:** este caso cuadra en el PDF y el respaldo aparece en ambas carpetas tras cerrar caja.

---

## Fase 6 · Entrega (visita al local)

```
Fase 6. Prepara la entrega:
1. Instalador final (Inno Setup) con versión en el nombre; actualizar sobre la versión preliminar conserva los datos
   que la dueña ya cargó (pruébalo instalando la preliminar, cargando datos y actualizando).
2. Modo de letra grande (RNF-04) y repaso de todos los textos de la UI: español claro, sin términos técnicos.
3. docs/guia-rapida.md y su PDF de UNA página para imprimir: vender, cobrar con vuelto, abrir y cerrar caja, registrar
   una compra, ver qué pedir, registrar un abono. Con atajos de teclado.
4. docs/lista-de-pruebas-en-sitio.md con los 12 criterios del PRD §7 en formato de casillas.
5. Revisión final con el "Prompt de revisión" sobre todo el proyecto.
```

### Lista para la visita

- [ ] Confirmar Windows 10/11 de 64 bits en la PC Samsung, memoria y disco libre (PRD P1).
- [ ] Instalar o actualizar; verificar que los productos ya cargados siguen ahí.
- [ ] Configurar impresora térmica 80 mm y probar nota de entrega y cierre.
- [ ] Probar lector de código de barras en venta y en ficha de producto.
- [ ] Instalar Google Drive para escritorio con la cuenta de la dueña y fijar la carpeta de nube; forzar un respaldo y
      verlo desde su celular junto con los PDF.
- [ ] Conectar a la UPS; probar desconectar la corriente de la UPS a mitad de una venta.
- [ ] Desconectar internet y hacer una venta completa.
- [ ] Recorrer con la dueña los 12 criterios del PRD §7 y firmar el acta de entrega.
- [ ] Capacitación 1 (dueña): productos, compras, ajustes, para pedir, reportes, resumen del mes, fiado, respaldo.
- [ ] Capacitación 2 (dueña + vendedor): vender, cobrar, vuelto, abonos, abrir y cerrar caja.
- [ ] Confirmar con la dueña que el fiado en USD le funciona (PRD P4).
- [ ] Dejar la guía rápida impresa junto a la computadora y acordar el acompañamiento por WhatsApp de la primera semana.
- [ ] Emitir la factura del Hito 3.
