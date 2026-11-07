# El programa en 10 minutos

Para Josner, antes de la visita. Léelo con calma y, si puedes, instala el programa en tu propia PC y úsalo en
**modo de prueba** (ver al final). No necesitas saber programar: solo entender qué hace cada pantalla.

## ¿Qué es y para quién?

**Borealis Repuestos** es el sistema de inventario, ventas y caja que hicimos para la tienda de repuestos de moto
**Romero Alfa 1** (Ciudad Bolívar). La dueña es **Yoleida Romero**. Lo que más le importa:

- Que el inventario **baje solo** con cada venta y suba con cada compra (un sistema anterior «cargaba pero nunca restaba»).
- Saber **qué le toca volver a pedir**.
- Ver cada mes **cuánto tiene invertido, cuánto compró, cuánto vendió y cuánto le quedó**.
- Que **no se pierda nada**: funciona sin internet, aguanta cortes de luz y se respalda solo en su Google Drive.

No tiene licencia que caduque: el programa es de ella. Es la promesa central de Borealis con este cliente.

## Palabras que vas a escuchar

| Palabra | Qué es |
|---|---|
| Tasa BCV | Bolívares por dólar del Banco Central. Se descarga sola de internet; si no hay internet, la dueña la escribe. |
| Precio | Cada producto tiene su precio en **dólares** (con IVA). El sistema lo pasa a bolívares con la tasa del día. |
| Caja | La gaveta del dinero. Se **abre** en la mañana con el efectivo que hay y se **cierra** en la tarde contándolo. Sin caja abierta no se vende. |
| Cierre ciego | Al cerrar, quien cierra escribe lo que contó **sin ver** cuánto debería haber. Solo la dueña ve la diferencia. |
| Nota de entrega | El ticket de cada venta (NE-000001, NE-000002…). **No es una factura fiscal.** Los números no se saltan nunca. |
| Fiado | Venta a crédito. La deuda se guarda en **dólares**. Los pagos parciales se llaman **abonos** (AB-000001…). |
| Para pedir | Lista de productos que llegaron a su mínimo. |
| Respaldo | Copia de seguridad de todos los datos. Se hace sola y se copia a Google Drive. |
| Dueña / vendedor | Dos tipos de usuario. El **vendedor** vende, cobra, abre y cierra caja, registra abonos; **no ve costos ni ganancias**. |

## La pantalla principal

Al entrar se ven botones grandes. La dueña ve todos; el vendedor solo los suyos.

| Botón | Para qué |
|---|---|
| **Vender (F5)** | La pantalla de venta. Se usa con el teclado y el lector de códigos. |
| **Productos (F3)** | Buscar y cargar productos. La dueña los crea y edita; el vendedor solo consulta. |
| **Caja** | Abrir, registrar salidas de efectivo y cerrar. |
| **Ventas del día** | Ver, reimprimir y anular notas del día. |
| **Compras** (dueña) | Registrar lo que llega de los proveedores: sube el inventario y actualiza el costo. |
| **Inventario** (dueña) | «Para pedir», ajustes (dañado, faltante, uso interno) y conteo físico. |
| **Fiado** | Clientes, deudores, abonos, estado de cuenta. |
| **Reportes** | PDF: ventas del día, monto vendido, **resumen del mes**, inventario valorizado, para pedir. |
| **Tasa BCV** | Ver la tasa y cargarla a mano si hace falta. |
| **Categorías, Usuarios, Configuración, Respaldo, Bitácora** (dueña) | Administración. |

Abajo, la **barra de estado** dice siempre: usuario, tasa, si la caja está abierta y cuándo fue el último respaldo.
Arriba de los botones salen **avisos** (sin tasa, caja cerrada, productos para pedir, fiado vencido, respaldo viejo).

## Una venta, de principio a fin

1. Caja → abrir con el efectivo que hay (por ejemplo 20 USD y Bs 500).
2. **F5** → escanear el producto (se agrega solo) o escribir «pastilla bera» y Enter.
3. **F9** para cobrar → **F2** efectivo USD → escribir 15 → Enter.
4. Si hay vuelto, escribir cuántos dólares se dan; el sistema dice el resto en bolívares.
5. **F9** → sale la nota de entrega por la impresora térmica.

## Modo de prueba (importante para la visita)

En el menú Inicio de Windows hay dos accesos:

- **Borealis Repuestos**: los datos **reales** de la tienda.
- **Borealis Repuestos (modo de prueba)**: una base **aparte**, con una franja amarilla que dice «MODO DE PRUEBA».
  Todo lo que hagas ahí no toca los datos reales. **Las pruebas y la práctica se hacen siempre en modo de prueba.**

> Por qué importa: si haces una venta de prueba en el modo real, ocupa la nota NE-000001 de la dueña para siempre
> (las notas anuladas conservan su número). En modo de prueba no pasa nada.

**Para practicar en tu PC:** instala `BorealisRepuestos-1.0.0-instalador.exe`, abre «(modo de prueba)», crea una dueña
de práctica (usuario `prueba`, clave `prueba123`), carga 3 productos, carga la tasa a mano en Tasa BCV, abre caja y
vende. Haz esto al menos una vez antes de la visita.
