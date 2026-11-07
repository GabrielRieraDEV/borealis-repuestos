# Reglas de negocio — Romero Alfa 1

Cada regla tiene un ID (RN-xx) que el código y las pruebas citan. Todas las cuentas se hacen con `Decimal`.
Notación: `HU(x, n)` = redondear `x` a `n` decimales con `ROUND_HALF_UP`. `TECHO(x, m)` = el menor múltiplo de `m`
que sea ≥ `x` (`ceil(x / m) × m`).

Datos de ejemplo usados en todo el documento: tasa **231,0468** Bs/USD, IVA **16 %**, múltiplo de redondeo **5,00 Bs**.

---

## RN-01 · Tasa vigente

- La tasa vigente es la de **fecha valor** más reciente que sea ≤ hoy. El BCV publica por adelantado (el viernes publica
  la del lunes), por eso se guarda la fecha valor y no la fecha de descarga.
- Descarga automática del sitio del BCV al arrancar y cada 2 horas. Si falla, se reintenta en silencio en el siguiente
  ciclo. No desactivar la verificación TLS: si el certificado del sitio falla, se registra en el log y queda la carga manual.
- Carga manual: la dueña escribe la tasa; se guarda con fecha valor = hoy y origen `MANUAL`. Si ya hay una tasa para esa
  fecha valor, la reemplaza y deja en bitácora la anterior.
- Si la tasa vigente tiene más de 3 días: aviso amarillo en la barra de estado, pero se puede vender.
- Si no existe ninguna tasa: no se puede abrir la pantalla de venta.
- Cada venta y cada abono guardan la tasa con la que se hicieron (`rate_e6`). Cambiar la tasa nunca modifica documentos ya guardados.

## RN-02 · Precio de venta

- La dueña fija el precio de venta de cada producto **en USD con IVA incluido** (`price_usd_e4`).
- Una sola lista de precios (público). Sin descuentos. El vendedor no puede cambiar precios.
- Todos los productos llevan IVA 16 % (`vat_rate_bp = 1600`). El campo existe por producto para el futuro.

## RN-03 · Precio unitario en bolívares

```
precio_bs = TECHO(price_usd × tasa, múltiplo)
```

- El redondeo es **siempre hacia arriba** para no perder margen. `múltiplo` se configura (por defecto 5,00 Bs; con 0,01
  queda el redondeo hacia arriba al céntimo).
- Ejemplo: 12,50 USD × 231,0468 = 2.888,085 → **Bs 2.890,00**.
- Ejemplo: 0,80 USD × 231,0468 = 184,83744 → **Bs 185,00**.
- Se calcula al agregar el renglón con la tasa vigente y queda guardado en el renglón (`unit_price_bs_e2`).

## RN-04 · Renglón de venta

```
total_renglón_bs  = HU(cantidad × precio_bs, 2)
total_renglón_usd = HU(cantidad × price_usd, 2)        (referencia)
costo_renglón_usd = HU(cantidad × costo_promedio_al_vender, 2)
```

- La cantidad admite decimales solo si el producto permite fracción (hasta 3 decimales).
- Ejemplo: 2,5 m de cable a Bs 185,00 → Bs 462,50.
- `unit_cost_usd_e4` del renglón guarda el costo promedio del producto **en el momento de la venta** (para el costo de lo
  vendido del mes; ver RN-13).

## RN-05 · Total, base e IVA de la venta

```
total_bs = Σ total_renglón_bs
base_bs  = HU(total_bs / 1,16, 2)
iva_bs   = total_bs − base_bs
total_usd = Σ total_renglón_usd
base_usd  = HU(total_usd / 1,16, 2)
```

- El IVA se calcula sobre el total del documento (no por renglón) para que base + IVA = total exacto.
- Ejemplo: total Bs 2.890,00 → base 2.491,38 (2.890 / 1,16 = 2.491,3793) → IVA 398,62.
- Si en el futuro hubiera productos con otra alícuota, se agrupa por alícuota y se aplica la misma fórmula a cada grupo.

## RN-06 · Pagos, vuelto y cierre del cobro

Formas de pago (`method`) y su moneda:

| method | Texto | Moneda | Cuenta como efectivo en caja |
|---|---|---|---|
| `CASH_VES` | Efectivo Bs | VES | Sí (Bs) |
| `CASH_USD` | Efectivo USD | USD | Sí (USD) |
| `POS` | Punto de venta | VES | No |
| `MOBILE` | Pago móvil | VES | No |
| `USDT` | Binance USDT (desactivado por defecto) | USD | No |
| `CREDIT` | Fiado | USD | No (genera deuda) |

```
equivalente_bs(pago) = monto                   si la moneda es VES
                     = HU(monto × tasa, 2)     si la moneda es USD
pagado_bs = Σ equivalente_bs(pagos sin vuelto)
falta_bs  = total_bs − pagado_bs
```

- La pantalla muestra lo que falta en Bs y su referencia en USD = `HU(falta_bs / tasa, 2)`.
- El cobro se puede cerrar cuando `pagado_bs ≥ total_bs`, o cuando el resto se va a fiado (RN-07).
- **Vuelto:** `vuelto_bs = pagado_bs − total_bs`. El usuario indica cuántos USD entrega (puede ser 0); el sistema
  calcula el resto en Bs: `vuelto_resto_bs = vuelto_bs − HU(vuelto_usd × tasa, 2)`. Si da negativo, no se permite
  (está dando de más). El vuelto se guarda como pagos con `is_change = 1` y monto **negativo** en su moneda.
- Ejemplo (criterio de aceptación 4): total Bs 2.890,00; paga 15 USD → equivalente 3.465,70 (15 × 231,0468 = 3.465,702).
  Vuelto Bs 575,70. Entrega 2 USD (= Bs 462,09) → resto **Bs 113,61**.
- USDT se convierte a la tasa BCV como si fuera USD (la tasa propia de USDT es de la opción Recomendada).
- IGTF: el parámetro `igtf_bp` existe (por defecto 0) y no se aplica en esta fase.

## RN-07 · Fiado

- Solo a clientes con `credit_enabled = 1`. "Consumidor final" nunca puede tener fiado.
- **La deuda se guarda en USD**, para que no pierda valor si sube la tasa:

```
deuda_usd = HU((total_bs − pagado_bs) / tasa_de_la_venta, 2)
```

- La venta guarda la parte fiada en Bs exacta (`credit_ves_e2 = total_bs − pagado_bs`) y en USD (`credit_usd_e2`).
- Ejemplo: venta de Bs 2.890,00 todo a fiado con tasa 231,0468 → 2.890 / 231,0468 = 12,5083 → **12,51 USD**.
- Vence en `fecha_venta + plazo_días` (del cliente o, si no tiene, el de la configuración: 15). Está vencida si hoy es
  posterior al vencimiento y el saldo es > 0.
- **Límite:** si el cliente tiene límite, `saldo_actual + deuda_nueva ≤ límite`. Si no, se bloquea salvo autorización de la dueña.
- **Abono:** se registra en cualquier forma de pago (excepto `CREDIT`) con la tasa vigente del día:

```
abono_usd = monto                         si la moneda es USD
          = HU(monto_bs / tasa_vigente, 2) si la moneda es VES
```

- Se aplica a la deuda más vieja primero (FIFO) hasta agotar el abono. No se permite abonar más que el saldo total.
- Ejemplo (criterio 6): con tasa 240,00 abona Bs 1.200,00 → 5,00 USD → saldo 7,51 USD.
- El abono entra a la caja abierta como cualquier pago (cuenta para el efectivo si es `CASH_VES` o `CASH_USD`).
- Anular la venta anula su deuda solo si aún no tiene abonos aplicados; si los tiene, la anulación se bloquea con
  el mensaje "La deuda de esta venta ya tiene abonos".

## RN-08 · Costo promedio ponderado

Al registrar cada renglón de compra (en orden):

```
si existencia_antes ≤ 0:  costo_nuevo = costo_compra
si no:                    costo_nuevo = HU((existencia_antes × costo_antes + cantidad × costo_compra)
                                           / (existencia_antes + cantidad), 4)
```

- Ejemplo (criterio 2): 7 u a 10,00 + 3 u a 12,00 → (70 + 36) / 10 = **10,6000 USD**.
- Ventas, ajustes y anulaciones de venta **no** cambian el costo promedio.
- Anular una compra resta las existencias pero no recalcula el costo hacia atrás (aproximación aceptada; la dueña puede
  corregir el costo a mano y queda en bitácora).
- **Compra por empaque:** `cantidad = empaques × unidades_por_empaque` y
  `costo_compra = HU(costo_empaque / unidades_por_empaque, 4)`. Ej.: 2 cajas de 12 bujías a 18,00 USD la caja →
  24 u a 1,5000 USD.
- La existencia siempre está en la unidad de venta del producto.
- Existencia inicial (RF-11): movimiento `INITIAL` con su costo; si es el primer movimiento, ese es el costo promedio.

## RN-09 · Existencias

- `stock_e3` del producto = suma de `qty_e3` de sus movimientos (invariante; la verifica `verify_stock`).
- Tipos de movimiento y signo: `INITIAL` (+), `PURCHASE` (+), `PURCHASE_VOID` (−), `SALE` (−), `SALE_VOID` (+),
  `ADJ_COUNT` (±), `ADJ_DAMAGE` (−), `ADJ_MISSING` (−), `ADJ_INTERNAL_USE` (−), `ADJ_CORRECTION_IN` (+).
- Con `allow_negative_stock = 0` (por defecto) una venta que deja existencia negativa no se puede cobrar; el mensaje dice
  qué producto y cuánto hay. Con la clave de la dueña se puede vender igual (queda en bitácora).
- Conteo físico: `diferencia = contado − existencia_sistema`; si ≠ 0 se registra un `ADJ_COUNT` por la diferencia.
- Cada movimiento guarda `stock_after_e3` (existencia resultante) para el kardex.

## RN-10 · Mínimo y "para pedir"

- Cada producto tiene `min_stock_e3` (por defecto 10 unidades, editable; 0 = sin alerta).
- Está "para pedir" si está activo y `stock ≤ min_stock` y `min_stock > 0`.
- La lista se agrupa por categoría y muestra el proveedor y el costo de la última compra.

## RN-11 · Caja

Por sesión de caja y por moneda:

```
esperado_usd = apertura_usd
             + Σ pagos CASH_USD de la sesión (ventas y abonos, incluido el vuelto negativo, sin anulados)
             + Σ entradas USD − Σ salidas USD
esperado_bs  = lo mismo con apertura_bs, CASH_VES y movimientos en Bs
diferencia   = contado − esperado          (positiva = sobra, negativa = falta)
```

- Ejemplo (criterio 5): apertura 20 USD y Bs 500,00; venta del ejemplo RN-06 (entra 15 USD, salen 2 USD y Bs 113,61) →
  esperado **33,00 USD** y **Bs 386,39**.
- Punto, pago móvil y USDT se listan por total y cantidad de operaciones para verificar contra el banco; no entran al arqueo.
- Cierre ciego: el vendedor escribe lo contado y ve "Cierre registrado"; solo la dueña ve esperado y diferencia.
- Solo puede haber una sesión `OPEN`. No se vende ni se abona sin sesión abierta.

## RN-12 · Numeración y nota de entrega

- Correlativos sin saltos, tomados dentro de la misma transacción del documento: notas `NE-000001`, abonos `AB-000001`.
  Una nota anulada conserva su número.
- Contenido de la nota de entrega (ticket 80 mm):
  - Razón social, RIF, domicilio fiscal y teléfono del negocio.
  - **"NOTA DE ENTREGA — NO VÁLIDA COMO FACTURA"**, número, fecha y hora, vendedor.
  - Cliente: nombre y cédula/RIF (o "Consumidor final").
  - Renglones: cantidad, descripción, precio unitario Bs, total Bs.
  - Base imponible, IVA 16 %, **Total Bs**; referencia USD y tasa BCV usada.
  - Formas de pago, vuelto y, si hubo fiado, monto fiado en USD y fecha de vencimiento.

## RN-13 · Resumen del mes (RF-82)

Para el mes M (fechas en hora local de Caracas). Las ventas y compras anuladas no cuentan.

| Línea | Fórmula |
|---|---|
| Inversión en mercancía al cierre del mes anterior | `inventory_value_usd` de la foto mensual de M−1 (si no existe: "sin dato") |
| Inversión en mercancía hoy | `Σ HU(max(existencia, 0) × costo_promedio, 2)` de productos activos |
| Compras del mes | `Σ total_usd` de compras con fecha en M |
| Ventas con IVA | `Σ total_usd` (y `Σ total_bs`) de ventas de M |
| IVA | `Σ (total_usd − base_usd)` (y en Bs `Σ vat_bs`) |
| Ventas netas | `Σ base_usd` |
| Costo de lo vendido | `Σ costo_renglón_usd` de los renglones de ventas de M |
| **Ganancia bruta** | Ventas netas − costo de lo vendido |
| Pérdidas | `Σ HU(|cantidad| × costo_promedio_del_momento, 2)` de ajustes `ADJ_DAMAGE`, `ADJ_MISSING`, `ADJ_INTERNAL_USE` en M; `ADJ_COUNT` negativo se muestra aparte como "faltantes de conteo" |
| Por cobrar (fiado) | Saldo total de deudas abiertas a la fecha |
| **Resultado del mes antes de gastos** | Ganancia bruta − pérdidas − faltantes de conteo |

- El reporte principal va en **USD** (sus costos son en USD); las ventas se muestran también en Bs.
- Tabla de los últimos 12 meses con: compras, ventas netas, ganancia bruta, resultado, inversión al cierre.
- **Foto mensual:** en el primer arranque de cada mes (antes de cualquier operación) se guarda en `monthly_snapshots`
  la inversión en mercancía calculada en ese momento como "cierre de M−1". Si el programa no se abrió el primer día,
  se toma igual en el primer arranque del mes y se marca la fecha real de la foto.
  No se toma foto si no hay movimientos de inventario anteriores al inicio del mes (base recién instalada): el reporte
  muestra "sin dato".
- El movimiento de ajuste guarda el costo promedio del momento (`unit_cost_usd_e4`) para valorizar las pérdidas.

## RN-14 · Anulaciones

| Documento | Quién | Cuándo | Efecto |
|---|---|---|---|
| Venta | Dueña, o vendedor con autorización | Mientras su sesión de caja esté abierta | `SALE_VOID` por cada renglón, pagos anulados, deuda anulada (si no tiene abonos) |
| Compra | Dueña | Siempre, si no deja existencias negativas | `PURCHASE_VOID` por renglón; el costo promedio no se toca |
| Abono | Dueña | Mientras su sesión de caja esté abierta | Revierte la aplicación a las deudas; el pago se anula |
| Ajuste | No se anula | — | Se corrige con otro ajuste |

Motivo obligatorio y registro en bitácora en todos los casos.

## RN-15 · Respaldo

- Archivo `romero_AAAAMMDD_HHMM.db` creado con `sqlite3.Connection.backup()`, verificado con `PRAGMA integrity_check`
  sobre la copia. Si la verificación falla, se borra la copia, se reintenta una vez y se avisa.
- Se conservan los 30 más recientes en `C:\ProgramData\BorealisRepuestos\respaldos\` y otros 30 en la carpeta de nube.
- Restaurar: primero respalda el estado actual con sufijo `_antes_de_restaurar`, luego reemplaza la base con el programa
  en modo exclusivo y reinicia.

## RN-16 · Bitácora

Se registran: inicio y cierre de sesión, intentos fallidos, alta y edición de usuarios, cambios de precio y costo (valor
antes y después), tasa manual, apertura y cierre de caja (con diferencias), entradas y salidas de efectivo, anulaciones,
ajustes y conteos, autorizaciones con clave de la dueña, ventas sin existencia, restauración de respaldo, cambios de configuración.
