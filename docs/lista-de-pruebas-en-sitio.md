# Lista de pruebas en sitio · Romero Alfa 1

Para la visita de instalación. Se recorre con la dueña y se firma al final. Cada criterio es el del PRD §7, con
pasos concretos y el valor exacto esperado. Marque ☑ cuando el resultado coincida.

**Antes de empezar:** caja abierta, tasa cargada a mano en **231,0468** (Tasa BCV → Cargar a mano; luego se deja
la automática), múltiplo de redondeo **5,00** (Configuración).

---

## A. Instalación

- [ ] Windows 10/11 de **64 bits** en la PC Samsung (Configuración de Windows → Sistema → Información). Memoria: ____ GB. Disco libre: ____ GB. (PRD P1)
- [ ] Ejecutar `BorealisRepuestos-1.0.0-instalador.exe` como administrador. Abre al terminar.
- [ ] Existen `C:\ProgramData\BorealisRepuestos\datos`, `respaldos` y `logs`.
- [ ] **Actualización conserva los datos** (si ya estaba la versión preliminar): antes de instalar, anotar cuántos
      productos hay (Productos, abajo a la izquierda): ____. Instalar la 1.0.0 encima. Abrir: la misma cantidad
      de productos, los mismos usuarios, la misma tasa. Ayuda → Acerca del programa dice **1.0.0**.
- [ ] Desinstalar y reinstalar **no** borra `C:\ProgramData\BorealisRepuestos` (solo si se hace la prueba en otra PC).

## B. Equipo

- [ ] Impresora térmica 80 mm instalada en Windows. Configuración → Impresora de tickets → elegirla →
      **Imprimir prueba**: sale completa, con acentos y eñes. Guardar.
- [ ] Lector de código de barras: en Productos, abrir una ficha y escanear en «Código de barras»: escribe el código
      y pasa al campo siguiente. En Vender, escanear el mismo producto: se agrega solo.
- [ ] Google Drive para escritorio con la cuenta de la dueña. Configuración → Carpeta de respaldo en la nube →
      una carpeta dentro de Google Drive. Respaldo → Respaldar ahora. En el celular de la dueña aparecen el
      archivo `romero_….db`, `Inventario de hoy.pdf` y `Resumen del mes.pdf`. (PRD P5)
- [ ] UPS conectada.

## C. Los 12 criterios de aceptación (PRD §7)

1. [ ] **El inventario resta.** Crear un producto de prueba con existencia **10**. Vender **3** → en Productos
   muestra **7**. Ventas del día → elegir la nota → Anular venta (motivo: prueba) → muestra **10**.
2. [ ] **La compra suma y promedia.** Producto con existencia **7** y costo **10,00**. Compras → Ctrl+N → comprar
   **3** a **12,00** → Ctrl+S. La ficha muestra **10** unidades y costo **10,60**.
3. [ ] **Precio en Bs.** Producto con precio **12,50** USD. En Vender, el precio sale **Bs 2.890,00**.
4. [ ] **Pago mixto y vuelto.** Vender ese producto (total **Bs 2.890,00**) → F9 → F2, **15** → Enter →
   «Entrega en USD»: **2** → el sistema indica **y en Bs: Bs 113,61** → F9.
5. [ ] **Caja cuadra.** Abrir caja con **20 USD** y **Bs 500,00**, hacer solo la venta del criterio 4. Como dueña,
   Caja → «Esperado ahora»: **USD 33,00** y **Bs 386,39**.
6. [ ] **Fiado en USD.** Fiado → Clientes → Nuevo cliente; Configurar fiado → «Puede comprar a fiado». Vender el
   producto de **12,50** a ese cliente (F3) → F9 → **F6** → F9: deuda **USD 12,51**. Cargar tasa a mano **240,00**.
   Fiado → Registrar abono → Efectivo Bs **1.200,00** → «Abona **USD 5,00** · el saldo queda en **USD 7,51**».
   Volver a dejar la tasa del día.
7. [ ] **Para pedir.** Producto con mínimo **10** y existencia **9** → aparece en Inventario → Para pedir y en el aviso
   de la pantalla principal.
8. [ ] **Resumen del mes.** Reportes → Resumen del mes: los totales coinciden con el cálculo a mano de las
   operaciones de prueba (ver el caso del plan, Fase 5: inversión 160,65; compras 65,00; ventas 47,00 /
   Bs 10.872,50; IVA 6,48; netas 40,52; costo 33,75; ganancia 6,77; pérdidas 0,60; resultado 6,17).
9. [ ] **Sin internet.** Desconectar el cable de red / Wi-Fi. Abrir caja, vender, imprimir la nota y cerrar caja.
   Todo funciona; la tasa queda la última guardada.
10. [ ] **Sin luz.** En medio de un cobro, desconectar la UPS de la pared y luego apagar la PC (o cerrar el programa
    desde el Administrador de tareas). Al volver a abrir: la venta **o está completa o no existe**, y la existencia
    cuadra (no aparece el aviso «existencias que no cuadran»).
11. [ ] **Permisos.** Usuarios → Nuevo vendedor. Entrar como vendedor: en Productos, Vender, Ventas del día y
    Reportes **no se ve ningún costo ni ganancia**; no aparecen Compras, Inventario, Configuración, Usuarios,
    Respaldo ni Bitácora; al cerrar caja solo ve «Cierre registrado».
12. [ ] **Respaldo.** Cerrar caja → aparece un respaldo nuevo en `C:\ProgramData\BorealisRepuestos\respaldos` y en la
    carpeta de Google Drive. Respaldo → Restaurar el elegido → escribir RESTAURAR → el programa se abre de nuevo con
    los datos de ese respaldo.

**Después de las pruebas:** borrar con un ajuste o anular lo que se creó de prueba, o (mejor) hacer las pruebas antes
de que la dueña cargue sus productos.

## D. Capacitación

- [ ] Sesión 1 (dueña): productos y carga rápida (Ctrl+Enter), compras, ajustes y conteo, para pedir, reportes,
      resumen del mes, fiado, respaldo, tasa manual.
- [ ] Sesión 2 (dueña + vendedor): vender con teclado y lector, cobrar, vuelto, abrir y cerrar caja, abonos.
- [ ] Confirmar con la dueña que el fiado en USD le sirve (PRD P4): ________________________________
- [ ] Guía rápida impresa junto a la computadora (`docs/guia-rapida.pdf`; también en Ayuda → Guía rápida).
- [ ] Acordado el acompañamiento por WhatsApp la primera semana.

---

Acta de entrega

Fecha: ____/____/________

Dueña: ______________________________ Firma: ______________________

Borealis Software Solutions: ______________________________ Firma: ______________________
