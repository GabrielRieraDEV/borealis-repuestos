# PRD — Sistema de inventario, ventas y caja · Romero Alfa 1

| | |
|---|---|
| Cliente | PARTES Y ACCESORIO DE MOTO ROMERO ALFA 1, F.P. — RIF V-31463591-0 |
| Contacto y aprobación | Yoleida Romero (dueña), por WhatsApp |
| Titular legal | Omega Celeste Contreras Romero |
| Proveedor | Borealis Software Solutions |
| Opción contratada | **Básica** — 300 USD, entrega en 4 días hábiles de desarrollo + instalación y capacitación |
| Versión | 1.0 · 07/11/2026 |
| Fuentes | Levantamiento del 28/10/2026, propuesta y alcance, audio de la clienta del 29/10/2026 |

---

## 1. Problema y objetivo

La tienda vende repuestos y accesorios de moto (más de 1.000 productos, casi todos genéricos) en Ciudad Bolívar.
Hoy no tiene sistema: lleva el control en cuaderno, fotos y WhatsApp. Antes pagó dos veces por soluciones que fallaron:
un sistema copiado que dejó de funcionar a la semana por la licencia, y un inventario que "cargaba la mercancía pero
nunca restaba".

En palabras de la dueña (29/10/2026):

> "Yo quiero un inventario que yo vendo, marco lo que vendo y que me vaya dando el tanto de lo que me queda, para yo
> volver a pedir. […] Para tener un control de lo que yo tengo ahí en inversión y de lo que yo meto todos los meses,
> lo que yo vendo todos los meses, lo que me va quedando. […] Si eso me va a durar, no se me va a borrar, no se me va a
> complicar, yo lo voy a comprar."

También le pasó que no pudo negociar la venta del negocio estando de viaje porque no sabía cuánta mercancía tenía.

**Objetivo:** que en cualquier momento la dueña sepa, sin contar a mano:

1. cuánto tiene de cada repuesto y qué le toca volver a pedir;
2. cuánto vendió hoy y si la caja cuadra, aunque ella no esté en el local;
3. cuánto tiene invertido en mercancía, cuánto compró, cuánto vendió y cuánto le quedó cada mes;
4. quién le debe y cuánto.

**Métricas de éxito (a los 30 días de uso):**

- La existencia que muestra el sistema coincide con el conteo físico en al menos 95 % de los productos contados.
- Todas las ventas del período están registradas con su nota de entrega (correlativos sin saltos).
- Cero pérdida de datos; respaldo fuera del local con antigüedad menor a 24 horas.
- La dueña genera sola el resumen del mes.

## 2. Usuarios y roles

| Rol | Quién | Uso |
|---|---|---|
| Dueña (`owner`) | Yoleida Romero | Todo: productos, precios, compras, ajustes, reportes, configuración, usuarios |
| Vendedor (`seller`) | Un empleado (por contratar) | Buscar, vender, cobrar, abrir y cerrar caja, registrar abonos |

Una sola computadora, una sola caja, un solo punto de venta. Comodidad con la computadora: media.

### Matriz de permisos

| Acción | Dueña | Vendedor |
|---|:-:|:-:|
| Buscar productos, ver existencia y precio | ✓ | ✓ |
| Ver costos, ganancias, inversión | ✓ | — |
| Crear y editar productos (sin precio ni costo) | ✓ | — |
| Cambiar precio o costo | ✓ | — |
| Registrar compras | ✓ | — |
| Ajustar inventario y conteos | ✓ | — |
| Vender y cobrar | ✓ | ✓ |
| Anular venta | ✓ | Solo con clave de la dueña en el momento |
| Abrir caja, registrar salidas de efectivo, cerrar caja | ✓ | ✓ |
| Ver diferencias del cierre de caja | ✓ | — |
| Vender a fiado y registrar abonos | ✓ | ✓ (solo a clientes con fiado habilitado y dentro del límite) |
| Habilitar fiado y fijar límite | ✓ | — |
| Ver sus propias ventas del día (montos, sin costos) | ✓ | ✓ |
| Reportes de inversión, mes, valorizado | ✓ | — |
| Configuración, usuarios, tasa manual, respaldo | ✓ | — |
| Ver bitácora | ✓ | — |

Toda acción que el vendedor no puede hacer se puede autorizar en el momento con la clave de la dueña
("Autorizar con clave de la dueña"); queda en la bitácora con ambos usuarios.

## 3. Alcance

### 3.1 Incluido (opción Básica)

Productos y búsqueda · tasa BCV automática y manual · compras con costo promedio · inventario que sube y baja solo,
ajustes, conteos y alertas de mínimo · ventas con pago mixto y vuelto en USD o Bs · nota de entrega impresa ·
caja con apertura, salidas y cierre ciego en USD y Bs · fiado con abonos y estado de cuenta · usuarios con permisos y
bitácora · reportes del día, monto vendido, **resumen del mes** e inventario valorizado · respaldo automático local y
en la nube · funcionamiento sin internet · instalación y capacitación.

> El **resumen del mes** y el **inventario valorizado** no estaban en la lista original de la Básica; se incluyen porque
> son el pedido central de la clienta en el audio del 29/10. No cambian el precio.

### 3.2 Fuera de alcance (no construir)

| Función | Dónde está | Nota |
|---|---|---|
| Facturación fiscal (factura y nota de crédito válidas ante el SENIAT) | Agregado aparte / Profesional | Ver §3.3 |
| Consulta en línea desde el celular | Recomendada | En la Básica se cubre en parte con los PDF en la carpeta de la nube (RF-92) |
| Precios automáticos por % de ganancia | Recomendada | En la Básica el precio en USD lo pone la dueña |
| Compras en USDT con su propia tasa | Recomendada | En la Básica el costo se registra directo en USD |
| Deudas y abonos a proveedores | Recomendada | |
| Kits que descuentan piezas | Recomendada | En la Básica un kit es un producto más |
| Cotizaciones y apartados | Recomendada | |
| Devoluciones con nota de crédito | Recomendada | En la Básica: anulación el mismo día (RF-53) o ajuste de inventario |
| Fechas de vencimiento | Recomendada | |
| Fotos de productos | Recomendada | |
| Ganancia por repuesto, más vendidos, sin rotación | Recomendada | |
| Etiquetas con código de barras, conteo por estante, segunda sucursal | Profesional | |
| Carga del catálogo | La hace la clienta | Borealis puede cotizarla aparte |
| Exportar a Excel | No pedido (P69) | |
| Gastos del negocio (alquiler, sueldos) | No pedido | El resumen del mes es "antes de gastos" |

### 3.3 Facturación fiscal: preparado, no implementado

La clienta quiere facturar desde el sistema (teme multas: a su distribuidor lo multaron). La norma está en transición:

- La Providencia SNAT/2026/00084 (G.O. 43.435, 12/08/2026) eliminó la obligación de usar sistemas homologados.
- La Providencia SNAT/2026/00093 (G.O. 43.484, 21/10/2026) deja la máquina fiscal como opcional y abre la emisión por la
  aplicación del SENIAT o por software de facturación digital, con un período de adecuación de unos 180 días.

**Decisión:** en esta fase el sistema emite **nota de entrega** (no fiscal) con la estructura de una factura, y la
clienta sigue facturando con su talonario de imprenta hasta que se active la facturación fiscal. El modelo de datos deja
campos preparados (`doc_type`, `control_number`, `fiscal_status`) sin lógica. La integración se cotiza cuando el SENIAT
publique los requisitos técnicos y la clienta elija el medio.

### 3.4 Pendientes que no bloquean el desarrollo

| # | Pendiente | Responsable | Bloquea |
|---|---|---|---|
| P1 | Versión de Windows de la PC Samsung (PySide6 exige Windows 10/11 de 64 bits) | Borealis en la visita | **El instalador final (Fase 6)** |
| P2 | Compra de impresora térmica 80 mm ESC/POS, UPS y lector | Clienta | Prueba de impresión en sitio |
| P3 | Fecha de arranque deseada | Clienta | Nada |
| P4 | Confirmar que el fiado se lleva en USD (RN-07) | Borealis en la capacitación | Nada |
| P5 | Carpeta de nube: cuenta de Google de la dueña con Google Drive para escritorio | Clienta + Borealis | RF-90 (solo la copia en la nube) |

## 4. Requisitos funcionales

Prioridad: **D** = debe estar para la entrega · **d** = debería estar; si el plazo aprieta, se entrega en la semana de
acompañamiento sin costo.

### 4.1 Acceso, usuarios y configuración

| ID | Requisito | Prio |
|---|---|---|
| RF-01 | Inicio de sesión con usuario y contraseña. Contraseñas con hash `scrypt` (stdlib). 5 intentos fallidos bloquean ese usuario 5 minutos. | D |
| RF-02 | Asistente de primer arranque: crea la cuenta de la dueña (la contraseña la elige ella, mínimo 6 caracteres), datos del negocio, múltiplo de redondeo, impresora y carpeta de respaldo en la nube. Ninguna contraseña viene precargada. | D |
| RF-03 | La dueña crea, desactiva y restablece la contraseña de vendedores. | D |
| RF-04 | Diálogo "Autorizar con clave de la dueña" para acciones restringidas hechas desde la sesión del vendedor. | D |
| RF-05 | Bitácora (`audit_log`) de acciones sensibles, consultable por la dueña con filtro por fecha, usuario y acción. | D |
| RF-06 | Configuración: razón social, RIF, domicilio fiscal (por defecto el del RIF), teléfono, múltiplo de redondeo, mínimo por defecto, plazo de fiado, formas de pago activas (Binance desactivada por defecto), impresora, carpeta de nube, permitir existencia negativa (no, por defecto), IGTF % (0, sin lógica). | D |

### 4.2 Productos

| ID | Requisito | Prio |
|---|---|---|
| RF-10 | Ficha de producto: código propio automático (`R-00001`), código de barras (opcional, único), nombre, marca del repuesto, modelos de moto compatibles (texto libre, ej. "Bera 150, Empire Owen 150"), categoría, estante, unidad (unidad, par, juego, docena, metro, litro), permite fracción (sí/no), costo USD, precio de venta USD con IVA, mínimo, activo. | D |
| RF-11 | Carga rápida: "Guardar y nuevo" (Ctrl+Enter) que conserva categoría, marca y estante del anterior; el foco vuelve al nombre; escanear llena el código de barras; existencia inicial + costo generan un movimiento `INITIAL`. Pensado para cargar 1.000 productos a mano. | D |
| RF-12 | Búsqueda en tiempo real por varias palabras en cualquier orden sobre nombre, marca, modelos compatibles, categoría, código y código de barras, sin distinguir mayúsculas ni acentos. "pastilla bera 150" encuentra "Pastillas de freno delanteras — Bera 150". Resultado: código, nombre, marca, modelos, estante, existencia, precio en Bs y USD; la dueña ve además el costo. Menos de 300 ms con 5.000 productos. | D |
| RF-13 | Edición de productos. Cambiar precio o costo solo la dueña; queda en bitácora con valor anterior y nuevo. | D |
| RF-14 | Categorías editables. Semilla: Motor, Frenos, Transmisión y arrastre, Eléctrico, Suspensión, Carrocería y plásticos, Cauchos y tripas, Accesorios, Herramientas, Repuestos de carro. | D |
| RF-15 | Desactivar productos (no se borran si tienen movimientos). Los inactivos no salen en la venta. | D |
| RF-16 | Ficha con pestaña "Movimientos" (kardex: fecha, tipo, cantidad, existencia resultante, usuario, documento) e "Historial de compras" (fecha, proveedor, factura, costo). | d |

### 4.3 Tasa BCV

| ID | Requisito | Prio |
|---|---|---|
| RF-20 | Descarga automática de la tasa oficial USD del BCV al arrancar y cada 2 horas mientras haya internet. Guarda la tasa con su fecha valor. Si la descarga falla, no interrumpe nada. | D |
| RF-21 | Carga manual de la tasa por la dueña (queda en bitácora). | D |
| RF-22 | La barra de estado muestra siempre la tasa vigente, su fecha valor y su origen (BCV automática / manual). Aviso si tiene más de 3 días. Sin ninguna tasa registrada, no se puede vender. Regla en RN-01. | D |

### 4.4 Compras

| ID | Requisito | Prio |
|---|---|---|
| RF-30 | Registrar compra: proveedor (elegir o crear rápido), número de factura del proveedor, fecha, renglones (producto, cantidad, costo unitario USD). Ayuda para compras por caja o docena: "N empaques × M unidades a X USD el empaque". Al guardar suben las existencias y se recalcula el costo promedio (RN-08). | D |
| RF-31 | Anular compra (dueña, con motivo): resta lo que había sumado. No recalcula el costo promedio hacia atrás. No se permite si deja alguna existencia negativa. | D |
| RF-32 | Lista de compras con filtro por fecha, proveedor y producto. | d |

### 4.5 Inventario

| ID | Requisito | Prio |
|---|---|---|
| RF-40 | Cada venta resta y cada compra suma, en la misma transacción que el documento. Existencia nunca negativa salvo que la configuración lo permita (RN-09). | D |
| RF-41 | Ajustes (dueña): dañado, faltante, uso interno, entrada por corrección. Cantidad y motivo obligatorios. | D |
| RF-42 | Conteo físico: la dueña elige productos (por categoría, estante o búsqueda), escribe lo contado y el sistema registra la diferencia como ajuste `COUNT`. | D |
| RF-43 | Alerta de mínimo: marca en la búsqueda, contador en la pantalla principal y lista **"Para pedir"** (existencia ≤ mínimo) por categoría y proveedor de la última compra, imprimible en PDF y ticket. | D |
| RF-44 | Herramienta `verify_stock`: compara `stock_e3` con la suma de movimientos y reporta diferencias. Se corre al arrancar (silenciosa si todo cuadra; si no, aviso a la dueña y bitácora). | D |

### 4.6 Ventas

| ID | Requisito | Prio |
|---|---|---|
| RF-50 | Pantalla de venta operable solo con teclado: F2 busca, escanear agrega, flechas y Enter eligen, cantidad editable (decimales si el producto permite fracción), Supr quita renglón, F9 cobra, Esc cancela. Muestra precio unitario en Bs (RN-03), total en Bs y referencia en USD, tasa usada y vendedor. Requiere caja abierta y tasa vigente. | D |
| RF-51 | Cliente: por defecto "Consumidor final". Se puede buscar o crear por cédula/RIF y nombre (P44). | D |
| RF-52 | Cobro con pagos mixtos: efectivo Bs, efectivo USD, punto de venta, pago móvil (referencia opcional), Binance USDT (si está activa), fiado. Muestra lo que falta en Bs y en USD. Vuelto en USD, en Bs o mezcla; el sistema calcula el resto (RN-06). | D |
| RF-53 | Anulación de venta mientras su caja sigue abierta: dueña o vendedor con autorización; motivo obligatorio. Devuelve existencias, anula los pagos y la deuda de fiado si la hubo. La nota conserva su número con la marca ANULADA. Ventas de cajas ya cerradas no se anulan: se corrigen con ajuste. | D |
| RF-54 | Nota de entrega impresa en ticket 80 mm al cobrar (y reimpresión). Contenido en RN-12. Si la impresora no responde, la venta queda guardada y se ofrece reimprimir o guardar PDF. | D |
| RF-55 | Sin descuentos y sin cambio de precio al vender (P37, P38). | D |
| RF-56 | Lista de ventas del día con su detalle y reimpresión. | D |

### 4.7 Caja

| ID | Requisito | Prio |
|---|---|---|
| RF-60 | Apertura con efectivo inicial en USD y en Bs. Una sola caja abierta a la vez. Si el programa se cierra con la caja abierta, al volver sigue la misma. | D |
| RF-61 | Entradas y salidas de efectivo (USD o Bs) con motivo, por cualquier usuario; la dueña las ve en el cierre. | D |
| RF-62 | Cierre ciego: quien cierra cuenta el efectivo en USD y en Bs y lo escribe. El vendedor no ve lo esperado ni la diferencia; la dueña sí. Se listan los totales de punto, pago móvil y Binance para verificar contra el banco. Imprime ticket de cierre y dispara un respaldo (RF-90). Fórmulas en RN-11. | D |
| RF-63 | Historial de cierres con diferencias (dueña). | D |

### 4.8 Fiado

| ID | Requisito | Prio |
|---|---|---|
| RF-70 | La dueña habilita fiado a un cliente, con límite opcional en USD y plazo en días (por defecto el de la configuración, 15). | D |
| RF-71 | Venta a fiado total o parcial (parte pagada y el resto fiado). La deuda se guarda en USD (RN-07). Bloqueo si supera el límite, salvo autorización de la dueña. | D |
| RF-72 | Abonos en cualquier forma de pago; se aplican a la deuda más vieja primero y entran a la caja abierta. Imprime comprobante de abono (`AB-000001`). | D |
| RF-73 | Estado de cuenta por cliente y lista de deudores con total por cobrar y vencidas resaltadas. | D |

### 4.9 Reportes (PDF, imprimibles)

| ID | Requisito | Prio |
|---|---|---|
| RF-80 | **Ventas del día:** número de notas, total Bs, referencia USD, desglose por forma de pago y por vendedor, anuladas aparte. El vendedor ve solo las suyas, sin costos. | D |
| RF-81 | **Monto vendido por período:** total con IVA, base e IVA en Bs, por día. Etiquetado "según notas de entrega (no fiscal)". | D |
| RF-82 | **Resumen del mes** (pedido central): inversión en mercancía al cierre del mes anterior y hoy, compras del mes, ventas con IVA, IVA, ventas netas, costo de lo vendido, ganancia bruta, pérdidas por ajustes, por cobrar y resultado del mes antes de gastos; con tabla de los últimos 12 meses. Fórmulas en RN-13. | D |
| RF-83 | **Inventario valorizado:** existencia × costo por producto y total, con lista de productos sin costo cargado. | D |
| RF-84 | **Para pedir** (ver RF-43). | D |

### 4.10 Respaldo

| ID | Requisito | Prio |
|---|---|---|
| RF-90 | Respaldo automático con la API de respaldo de SQLite: al arrancar (si el último tiene más de 12 h), al cerrar caja y al salir. Verifica el archivo con `PRAGMA integrity_check`. Guarda los últimos 30 en la carpeta local y copia cada uno a la carpeta de la nube (Google Drive para escritorio). La barra de estado muestra la hora del último respaldo en la nube; aviso si pasa de 48 h. | D |
| RF-91 | Restaurar un respaldo (dueña, con doble confirmación; antes guarda una copia del estado actual). | D |
| RF-92 | Al cerrar caja y al salir, deja en la carpeta de la nube `Inventario de hoy.pdf` y `Resumen del mes.pdf`, para que la dueña los abra desde el celular con la app de Google Drive. | d |

## 5. Requisitos no funcionales

| ID | Requisito |
|---|---|
| RNF-01 | **Sin licencia que caduque.** El programa no tiene activación, verificación en línea, fecha de vencimiento ni bloqueo remoto. (Es la promesa central de la propuesta.) |
| RNF-02 | Funciona completo sin internet. Internet solo para la tasa BCV y la sincronización de la carpeta de nube (la hace Google Drive). |
| RNF-03 | Durabilidad ante cortes de luz: SQLite WAL con `synchronous=FULL`, una transacción por operación. Probado cortando el proceso a mitad de una venta (RF de prueba en el plan). |
| RNF-04 | Windows 10/11 de 64 bits, resolución mínima 1366×768, opción de letra grande. |
| RNF-05 | Arranque en menos de 5 s; búsqueda en menos de 300 ms; guardar una venta en menos de 1 s, con 5.000 productos y 50.000 ventas. |
| RNF-06 | Datos en `C:\ProgramData\BorealisRepuestos\` (base, respaldos, logs). El instalador da permiso de escritura a los usuarios y las actualizaciones nunca tocan esa carpeta. |
| RNF-07 | Log técnico rotativo (5 archivos de 1 MB) sin datos de clientes ni contraseñas. |
| RNF-08 | Textos en español de Venezuela; formato `Bs 1.234,56`, `USD 12,50`, `dd/mm/aaaa`. |
| RNF-09 | Pruebas automáticas de todas las reglas de `02-reglas-de-negocio.md` y de los escenarios del §7. |

## 6. Pantallas

1. Inicio de sesión y asistente de primer arranque.
2. Principal: accesos grandes (Vender, Buscar, Productos, Compras, Caja, Fiado, Reportes) + avisos (para pedir, deudas vencidas, tasa vieja, respaldo viejo). Barra de estado: usuario, tasa, caja, último respaldo.
3. Venta y cobro.
4. Productos: lista con búsqueda y ficha (datos, movimientos, compras).
5. Compras: lista y registro.
6. Inventario: ajustes, conteo, para pedir.
7. Caja: apertura, entradas/salidas, cierre, historial.
8. Clientes y fiado: lista de deudores, estado de cuenta, abono.
9. Reportes.
10. Configuración: negocio, usuarios, tasa, impresora, respaldo, bitácora.

## 7. Criterios de aceptación (se prueban con la dueña en la entrega)

1. **El inventario resta.** Producto con existencia 10; se venden 3 → muestra 7. Se anula la venta → muestra 10.
2. **La compra suma y promedia.** Existencia 7 a 10,00 USD; se compran 3 a 12,00 USD → 10 unidades a 10,60 USD.
3. **Precio en Bs.** Precio 12,50 USD, tasa 231,0468, múltiplo 5 → cobra Bs 2.890,00.
4. **Pago mixto y vuelto.** Total Bs 2.890,00; paga 15 USD en efectivo; recibe 2 USD y el resto en Bs → el sistema indica Bs 113,61.
5. **Caja cuadra.** Apertura 20 USD y Bs 500; ventas del ejemplo anterior → esperado en caja 33 USD y Bs 386,39.
6. **Fiado en USD.** Venta a fiado de Bs 2.890,00 a tasa 231,0468 → deuda 12,51 USD. Con tasa 240,00 abona Bs 1.200,00 → abona 5,00 USD, saldo 7,51 USD.
7. **Para pedir.** Producto con mínimo 10 y existencia 9 aparece en "Para pedir".
8. **Resumen del mes.** Con las operaciones de prueba del plan (Fase 5), los totales coinciden con el cálculo a mano.
9. **Sin internet.** Con el cable de red desconectado se abre caja, se vende, se imprime y se cierra.
10. **Sin luz.** Se mata el proceso en medio de un cobro: al reabrir, la base pasa `integrity_check` y la venta o está completa o no existe; la existencia cuadra (`verify_stock`).
11. **Permisos.** Con el usuario vendedor no se ve ningún costo ni ganancia en ninguna pantalla ni reporte.
12. **Respaldo.** Tras cerrar caja aparece un respaldo nuevo en la carpeta local y en la de la nube, y se puede restaurar.

## 8. Entrega, capacitación y pagos

| Hito | Contenido | Pago |
|---|---|---|
| Anticipo | Firma | 50 % — 150 USD |
| Hito 2 | Productos instalados para empezar la carga (Fase 1) y ventas, caja e inventario funcionando (Fases 2–3) | 25 % — 75 USD |
| Hito 3 | Instalación final, fiado, reportes, respaldo, capacitación | 25 % — 75 USD |

Capacitación (respuesta a "¿tú me vas a venir a ayudar esos días?"): dos sesiones en el local (dueña y vendedor),
guía rápida de una página impresa y acompañamiento por WhatsApp la primera semana. Garantía de 60 días sobre lo descrito
en este documento.
