# Pruebas en sitio · los 12 criterios de aceptación

Para Josner, con la dueña al lado. **Todo se hace en «Borealis Repuestos (modo de prueba)»** (franja amarilla arriba).
Sigue el orden: el bloque A va primero porque sus números solo dan exactos con la base vacía.
Marca ☑ solo si ves **exactamente** el valor en negrita. Si no coincide, anota lo que viste y sigue; al final se lo
mandas a Gabriel.

Teclas útiles: **F5** vender · **F9** cobrar · **F2** efectivo USD · **F3** punto de venta · **F6** fiado ·
**Ctrl+N** nuevo · **Ctrl+S** guardar · **Esc** volver.

## Preparación (5 min)

- [ ] Abrir «Borealis Repuestos (modo de prueba)». Crear la dueña de práctica: usuario `prueba`, clave `prueba123`.
      Razón social: déjala como viene. Múltiplo de redondeo: **5,00**.
- [ ] Configuración → Impresora de tickets → la térmica → Guardar.
- [ ] Tasa BCV → «Cargar a mano»: **231,0468** → Guardar tasa de hoy.

## Bloque A · Resumen del mes (criterio 8)

1. Productos → **Nuevo producto (Ctrl+N)**:
   - Nombre «Pastillas de freno Bera 150», precio **15**, costo **10**, existencia inicial **10** → **Ctrl+Enter**
     (guarda y abre otra ficha).
   - Nombre «Cable eléctrico», unidad **Metro** (se marca «por fracción»), precio **0,80**, costo **0,30**,
     existencia inicial **100** → **Ctrl+S**.
2. Compras → **Ctrl+N** → «Nuevo proveedor…»: «Proveedor de prueba». Producto: escribe «pastillas» y Enter →
   cantidad **5** Enter → costo **13** Enter → **Ctrl+S**.
3. Caja → abrir con **0** USD y **0** Bs.
4. **F5** → «pastillas» Enter → cantidad **3** Enter → «cable» Enter → cantidad **2,5** Enter. El total debe decir
   **TOTAL Bs 10.872,50**. **F9** → **F3** (punto) → Enter (completa) → **F9**. Sale la nota.
5. Inventario → pestaña Ajuste → «cable» Enter → tipo **Dañado**, cantidad **2**, motivo «prueba» → Guardar ajuste.
6. **F5** → «pastillas» Enter → cantidad **1** Enter → F9 → F3 → Enter → F9. Luego **Ventas del día** → elige esa
   nota (la última) → **Anular venta…** → motivo «prueba».
7. Reportes → **Resumen del mes** → Ver:

- [ ] **8. Resumen del mes.** Inversión al cierre del mes anterior **sin dato** · Inversión hoy **USD 160,65** ·
  Compras **USD 65,00** · Ventas con IVA **USD 47,00** y **Bs 10.872,50** · IVA **USD 6,48** · Ventas netas
  **USD 40,52** · Costo de lo vendido **USD 33,75** · Ganancia bruta **USD 6,77** · Pérdidas **USD 0,60** ·
  Resultado **USD 6,17**.

8. Caja → **Cerrar caja…** → contado **0** y **0** → Cerrar caja.

## Bloque B · Precio, cobro, vuelto y caja

9. Productos → Nuevo: «Producto de prueba», precio **12,50**, costo **10**, existencia inicial **20** → Ctrl+S.
10. Caja → abrir con **20** USD y **500** Bs.

- [ ] **3. Precio en Bs.** F5 → «producto de prueba» Enter → cantidad 1 Enter. Precio: **2.890,00** y total
  **Bs 2.890,00**.
- [ ] **4. Pago mixto y vuelto.** F9 → **F2** → **15** → Enter → en «Entrega en USD» escribe **2**. Debe decir
  **→ y en Bs: Bs 113,61**. → **F9**.
- [ ] **5. Caja cuadra.** Caja: «Esperado ahora» **USD 33,00** y **Bs 386,39**.

## Bloque C · Inventario

- [ ] **1. El inventario resta.** Productos → Nuevo: «Prueba resta», precio 1, existencia inicial **10** → Ctrl+S.
  F5 → «prueba resta» → cantidad **3** → F9 → F3 → Enter → F9. Productos → «prueba resta»: existencia **7 u**.
  Ventas del día → esa nota → Anular venta… → motivo «prueba». Productos: existencia **10 u**.
- [ ] **2. La compra suma y promedia.** Productos → Nuevo: «Prueba compra», precio 20, costo **10**, existencia
  inicial **7** → Ctrl+S. Compras → Ctrl+N → Proveedor de prueba → «prueba compra» → cantidad **3** → costo **12** →
  Ctrl+S. Productos → abrir «Prueba compra»: existencia **10 u** y costo **10,60**.
- [ ] **7. Para pedir.** Productos → Nuevo: «Prueba pedir», precio 1, **mínimo 10**, existencia inicial **9** →
  Ctrl+S. Inventario → Para pedir: aparece «Prueba pedir». La pantalla principal dice «Para pedir: …».

## Bloque D · Fiado

- [ ] **6. Fiado en USD.** Fiado → Clientes → **Nuevo cliente**: cédula **12345678**, nombre «Cliente prueba» →
  Crear cliente. Elegirlo → **Configurar fiado…** → marcar «Puede comprar a fiado» → Guardar.
  F5 → **F3** → escribe 12345678 → Enter → elígelo. Agrega «producto de prueba» (Bs 2.890,00) → F9 → **F6** → F9.
  Fiado → Deudores: «Cliente prueba» debe **USD 12,51**.
  Tasa BCV → Cargar a mano **240** → Guardar. Fiado → Deudores → Cliente prueba → Registrar abono → Efectivo Bs →
  **1200**: debe decir «Abona **USD 5,00** · el saldo queda en **USD 7,51**» → Guardar abono (sale el comprobante).
  Vuelve a cargar la tasa en **231,0468**.

## Bloque E · Sin internet, sin luz, permisos y respaldo

- [ ] **9. Sin internet.** Desconecta el cable de red y apaga el Wi-Fi. F5 → vende «producto de prueba» → F9 → F3 →
  Enter → F9: **sale la nota**. Caja → Cerrar caja (cuenta lo que diga el cajón de prueba). Todo funciona.
  Reconecta internet.
- [ ] **10. Sin luz.** Caja → abrir con 0 y 0. F5 → «producto de prueba» → F9 → F3 → Enter → pulsa **F9** y
  enseguida **mantén apretado el botón de encendido de la PC 5 segundos** (apagado forzado, como un corte de luz).
  Enciende la PC y abre el modo de prueba. Ventas del día: la última venta **está completa o no está** (no hay
  ventas a medias) y **no sale** el aviso «existencias que no cuadran».
- [ ] **11. Permisos.** Usuarios → Nuevo vendedor: usuario `vende`, clave `vende123`. Sesión → Cerrar sesión → entra
  como `vende`. En Productos, Vender, Ventas del día y Reportes **no aparece ningún costo ni ganancia**; no están los
  botones Compras, Inventario, Configuración, Usuarios, Respaldo ni Bitácora. Caja → Cerrar caja… → solo dice
  **«Cierre registrado»** (sin esperado ni diferencia). Vuelve a entrar como `prueba`.
- [ ] **12. Respaldo.** Respaldo → la lista tiene un respaldo con la hora del último cierre de caja. Elígelo →
  **Restaurar el elegido…** → Sí → escribe **RESTAURAR**. El programa se cierra y **se abre solo**, todavía en
  modo de prueba, con los datos de ese momento. (La copia en Google Drive ya se probó en la guía, paso 8.)

## Extra · Recuperar la clave de la dueña (práctica)

- [ ] Al crear la dueña de práctica salió un código de recuperación: anótalo en una hoja aparte (es solo de prueba).
  Sesión → Cerrar sesión → **«¿Olvidó la clave de la dueña?»** → escribe ese código y la clave nueva `prueba456`
  dos veces → Cambiar la clave. Debe decir «Listo» y mostrar un **código nuevo**. Entra como `prueba` con
  `prueba456`: funciona. Enséñale a la dueña este procedimiento.

## Resultado

Criterios cumplidos: ____ de 12. Lo que no coincidió (criterio, qué se esperaba, qué se vio):

________________________________________________________________________________

________________________________________________________________________________

---

## Acta de entrega

En Ciudad Bolívar, a los ____ días de ______________ de 20____, se instala el sistema **Borealis Repuestos 1.0.0**
en PARTES Y ACCESORIO DE MOTO ROMERO ALFA 1, F.P. (RIF V-31463591-0). Se recorrieron los criterios de aceptación
con el resultado anotado arriba, se configuraron la impresora, el lector y el respaldo en Google Drive, y se dio la
capacitación a la dueña y al vendedor.

El fiado se lleva en dólares (deuda en USD con la tasa del día de la venta): ☐ De acuerdo ☐ Pide cambio: __________

Pendientes acordados: __________________________________________________________

Dueña: Yoleida Romero · C.I. ____________ · Firma: ______________________

Por Borealis Software Solutions: Josner ____________ · Firma: ______________________
