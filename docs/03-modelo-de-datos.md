# Modelo de datos — Romero Alfa 1

Base SQLite única en `C:\ProgramData\BorealisRepuestos\datos\romero.db`. El DDL completo está en `docs/schema.sql`
(es la migración `0001`). Este documento explica las tablas, las escalas y las invariantes que el código debe respetar.

## Escalas de enteros

| Sufijo | Qué guarda | Escala | Decimales | Ejemplo |
|---|---|---|---|---|
| `_e4` | Precio o costo unitario USD | ×10.000 | 4 | 10,6000 USD → `106000` |
| `_e2` | Montos y totales (USD o Bs) | ×100 | 2 | Bs 2.890,00 → `289000` |
| `_e3` | Cantidades y existencias | ×1.000 | 3 | 2,5 m → `2500` |
| `_e6` | Tasa Bs por USD | ×1.000.000 | 6 | 231,0468 → `231046800` |
| `_bp` | Porcentajes | ×100 | 2 | 16 % → `1600` |

`_ves_` = bolívares, `_usd_` = dólares. Conversión solo en `db/repositories` con helpers
`to_db(Decimal, scale) -> int` (lanza error si el valor tiene más decimales que la escala: redondear antes, en el dominio)
y `from_db(int, scale) -> Decimal`.

## Mapa de tablas

```
users ─┬─< audit_log
       ├─< cash_sessions ─┬─< cash_movements
       │                  ├─< sales ─┬─< sale_items >── products ──< inventory_movements
       │                  │          ├─< payments                  │
       │                  │          └── receivables >── customers  ├── categories
       │                  ├─< credit_payments ─< credit_allocations >── receivables
       │                  └─< payments (de abonos)                  └─< purchase_items >── purchases >── suppliers
exchange_rates   settings   doc_sequences   monthly_snapshots   schema_migrations
```

## Tablas

| Tabla | Propósito | Notas |
|---|---|---|
| `settings` | Configuración clave-valor | Valores como texto; el servicio de configuración los tipa. Claves en `schema.sql`. |
| `doc_sequences` | Correlativos `NE`, `AB`, `R` | Leer y aumentar en la misma transacción del documento (`UPDATE … SET next_number = next_number + 1 RETURNING`). |
| `users` | Dueña y vendedores | `role` `owner`/`seller`. Hash `scrypt` de `hashlib`. |
| `audit_log` | Bitácora (RN-16) | `authorized_by` cuando la dueña autoriza con su clave. `details_json` con antes/después y motivo. |
| `categories` | Categorías editables | Semilla en `schema.sql`. |
| `products` | Catálogo | `stock_e3` es caché; ver invariante 1. `search_text` se regenera al guardar (minúsculas, sin acentos, une nombre, marca, modelos, categoría, código y barras). |
| `exchange_rates` | Tasa BCV | Una fila por fecha valor. Vigente = mayor `valid_date ≤ hoy` (RN-01). |
| `suppliers`, `purchases`, `purchase_items` | Compras | `total_usd_e2 = Σ line_total_usd_e2`. |
| `customers` | Clientes | `id = 1` es "Consumidor final" (sin fiado, no se edita ni desactiva). |
| `cash_sessions`, `cash_movements` | Caja | Índice único parcial: una sola sesión `OPEN`. Al cerrar se guardan esperado y contado. |
| `sales`, `sale_items` | Ventas (notas de entrega) | Copias de precio, costo y descripción al vender. `control_number` y `fiscal_status` preparados, sin uso. |
| `payments` | Pagos de ventas **y** de abonos | Exactamente uno de `sale_id` o `credit_payment_id`. Vuelto = fila con `is_change = 1` y monto negativo. `CREDIT` no es una fila de pago: la parte fiada vive en `sales.credit_ves_e2` / `credit_usd_e2` y en `receivables`. |
| `receivables` | Deudas por fiado | Una por venta con fiado. `balance_usd_e2` baja con las asignaciones. |
| `credit_payments`, `credit_allocations` | Abonos y su reparto FIFO | Un abono puede repartirse en varias deudas. |
| `inventory_movements` | Kardex | Fuente de verdad de existencias. Cantidad con signo según el tipo (CHECK). |
| `monthly_snapshots` | Inversión al cierre de cada mes | Una fila por mes (RN-13). |

## Invariantes (cada una con prueba en `tests/test_invariants.py`)

1. **Existencia:** para todo producto, `stock_e3 = Σ inventory_movements.qty_e3`. Y el `stock_after_e3` del último
   movimiento = `stock_e3`.
2. **Venta:** `total_ves_e2 = Σ sale_items.line_total_ves_e2`, `total_usd_e2 = Σ line_total_usd_e2`,
   `base_ves_e2 + vat_ves_e2 = total_ves_e2` (este último también es CHECK).
3. **Cobro completo:** para una venta `COMPLETED`,
   `Σ payments.amount_ves_e2 (no anulados, incluido el vuelto) + credit_ves_e2 = total_ves_e2`, exacto.
   `credit_usd_e2 = HU(credit_ves / tasa, 2)` (RN-07); la deuda se cobra en USD, `credit_ves_e2` es solo para cuadrar.
4. **Fiado:** `receivables.balance_usd_e2 = amount_usd_e2 − Σ credit_allocations.amount_usd_e2` (de abonos no anulados);
   `status = 'PAID'` si y solo si el saldo es 0.
5. **Abono:** `credit_payments.amount_usd_e2 = Σ credit_allocations.amount_usd_e2` del abono.
6. **Caja:** a lo sumo una sesión `OPEN`; toda venta, pago, abono y movimiento de caja apunta a una sesión que estaba
   abierta al crearse.
7. **Correlativos:** los `number` de `sales` (por `doc_type`) y de `credit_payments` son 1..N sin huecos.
8. **Anulación:** una venta `VOIDED` tiene un `SALE_VOID` por cada `SALE`, todos sus pagos con `voided = 1` y su deuda
   (si existe) en `VOIDED`.

## Transacciones por caso de uso

| Caso de uso | Escribe en una sola transacción |
|---|---|
| Crear producto con existencia inicial | `products`, `doc_sequences('R')`, `inventory_movements(INITIAL)`, `audit_log` |
| Registrar compra | `purchases`, `purchase_items`, `inventory_movements(PURCHASE)`, `products` (stock y costo) |
| Cobrar venta | `doc_sequences('NE')`, `sales`, `sale_items`, `payments`, `inventory_movements(SALE)`, `products.stock_e3`, `receivables` (si hay fiado), `audit_log` (si se vendió sin existencia) |
| Anular venta | `sales`, `payments.voided`, `inventory_movements(SALE_VOID)`, `products.stock_e3`, `receivables`, `audit_log` |
| Abono | `doc_sequences('AB')`, `credit_payments`, `credit_allocations`, `receivables`, `payments` |
| Ajuste o conteo | `inventory_movements(ADJ_*)`, `products.stock_e3`, `audit_log` |
| Cerrar caja | `cash_sessions`, `audit_log` (el respaldo va **después** del commit) |

Todas con `BEGIN IMMEDIATE`. La impresión y el respaldo ocurren después del `COMMIT` y su falla nunca revierte el documento.

## Consultas clave (orientativas)

```sql
-- Tasa vigente (RN-01)
SELECT rate_e6, valid_date, source FROM exchange_rates
WHERE valid_date <= date('now','localtime') ORDER BY valid_date DESC LIMIT 1;

-- Para pedir (RN-10)
SELECT * FROM products WHERE active = 1 AND min_stock_e3 > 0 AND stock_e3 <= min_stock_e3;

-- Esperado en caja USD (RN-11)
SELECT s.opening_usd_e2
     + COALESCE((SELECT SUM(amount_e2) FROM payments
                 WHERE session_id = s.id AND method = 'CASH_USD' AND voided = 0), 0)
     + COALESCE((SELECT SUM(CASE direction WHEN 'IN' THEN amount_e2 ELSE -amount_e2 END)
                 FROM cash_movements WHERE session_id = s.id AND currency = 'USD'), 0)
FROM cash_sessions s WHERE s.id = ?;

-- Verificación de existencias (RF-44)
SELECT p.id, p.code, p.stock_e3, COALESCE(SUM(m.qty_e3), 0) AS ledger
FROM products p LEFT JOIN inventory_movements m ON m.product_id = p.id
GROUP BY p.id HAVING p.stock_e3 <> ledger;
```

## Preparado para fases futuras (no implementar ahora)

- `sales.doc_type` admitirá `'FAC'`; `control_number` y `fiscal_status` para la facturación fiscal.
- `settings.igtf_bp` para el IGTF.
- `products.vat_rate_bp` por producto para alícuotas distintas.
- Las opciones Recomendada y Profesional agregan tablas nuevas (proveedores con deuda, kits, apartados, fotos);
  no reutilizar columnas existentes para eso.
