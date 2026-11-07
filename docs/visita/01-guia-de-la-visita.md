# Guía de la visita · paso a paso

Para Josner. Sigue los pasos en orden y marca cada casilla. Si algo no sale como dice «Debe pasar», busca el número en
**04 · Problemas y soluciones** y, si no se resuelve, escríbele a Gabriel por WhatsApp (________________) con una
foto de la pantalla. **No improvises con los datos de la dueña.**

Tiempo total: unas 4 horas (instalación y pruebas 2 h, capacitación 1 h 45 min, cierre 15 min).

## Lo que ya sabemos de la PC

- Windows **10** (por la foto). Monitor Samsung SyncMaster de 17″ (1440×900): suficiente.
- Tiene Chrome, Firefox, Edge y **Acrobat Reader** (los PDF abren sin instalar nada).
- **Falta confirmar que sea de 64 bits** (paso 2). Si es de 32 bits, el programa **no instala**: avisa a Gabriel antes
  de seguir.

## 1. Antes de salir

- [ ] Pendrive con: `BorealisRepuestos-1.0.0-instalador.exe` y la carpeta `docs/visita` en PDF.
- [ ] Impresos: **guía rápida** (2 copias: una se queda pegada junto a la PC), **lista de pruebas** y el **acta**.
- [ ] Practicaste una venta en modo de prueba en tu PC (ver «00 · El programa en 10 minutos»).
- [ ] Confirmaste con la dueña: que tenga a mano la impresora térmica, el lector, la UPS, el cable USB de cada uno,
      la clave de su cuenta de Google (Gmail) y que el vendedor pueda estar en la capacitación 2.
- [ ] El número de WhatsApp de Gabriel anotado arriba.

## 2. Revisar la PC (10 min)

- [ ] Inicio → Configuración → Sistema → **Acerca de**. En «Tipo de sistema» debe decir
      **«Sistema operativo de 64 bits»**. Anota: ______ bits. Memoria (RAM instalada): ______ GB.
- [ ] Explorador de archivos → Este equipo → disco C: con **al menos 2 GB libres**. Libres: ______ GB.
- [ ] Fecha y hora de Windows correctas (abajo a la derecha). Si están mal, corrígelas: el sistema usa la fecha para
      la tasa, la caja y los reportes.
- [ ] Internet funciona (abre google.com en Chrome).

## 3. Instalar (10 min)

- [ ] Copia el instalador del pendrive al Escritorio y ábrelo con doble clic.
- [ ] Si sale **«Windows protegió su PC»** (pantalla azul): clic en **«Más información»** → **«Ejecutar de todas
      formas»**. Es normal: el instalador no tiene firma comercial.
- [ ] Si pide permiso de administrador: **Sí**.
- [ ] En «Accesos directos», deja marcadas **las dos** casillas (escritorio y modo de prueba). Siguiente → Instalar.
- [ ] Debe pasar: en el escritorio quedan **«Borealis Repuestos»** y **«Borealis Repuestos (modo de prueba)»**.

**Si ya estaba instalada la versión preliminar** (la dueña ya cargó productos):

- [ ] Antes de instalar, abre el programa normal, entra a Productos y anota cuántos productos dice abajo a la
      izquierda: ______. Cierra el programa.
- [ ] Instala encima (mismos pasos). Abre el programa normal: misma cantidad de productos, mismos usuarios.
      Ayuda → Acerca del programa dice **versión 1.0.0**. Si falta algo, **no sigas** y avisa a Gabriel.

## 4. Primer arranque real, con la dueña (10 min)

Abre **«Borealis Repuestos»** (el normal). Si ya tenía la preliminar, este paso no aparece: salta al 5.

- [ ] Sale el asistente «Configuración inicial». **La dueña escribe** su nombre, su usuario y **su contraseña**
      (mínimo 6 letras o números). **Tú no la escribas ni la anotes.** Recomiéndale anotarla en un papel guardado.
- [ ] Datos del negocio: razón social y RIF ya vienen escritos; revisa con ella el **domicilio fiscal** y el
      **teléfono** (salen en cada nota de entrega).
- [ ] Múltiplo de redondeo: **5,00**. Impresora y carpeta de la nube: déjalas en blanco por ahora → Terminar.
- [ ] Sale el **código de recuperación** (tipo `K7QM-3XR9-PW2H`) en un recuadro amarillo. Es lo único que le permite
      recuperar su clave si la olvida, y **no se vuelve a mostrar**. Que **la dueña** lo copie en un papel, letra por
      letra; revisen juntos que esté igual. Que lo guarde en casa o en un sobre, **no pegado en la PC**. **No le tomes
      foto ni lo anotes tú.** Ella marca «Ya lo anoté en papel» → Continuar.
- [ ] Debe pasar: pide usuario y contraseña; la dueña entra y ve «Hola, Yoleida…».
- [ ] **Si ya tenía la versión preliminar:** en la pantalla principal sale el aviso «Falta el código de recuperación».
      Usuarios → **Código de recuperación…** → Sí → mismo procedimiento del papel.

## 5. Impresora térmica (20 min)

- [ ] Conecta la impresora por USB, enciéndela y pon papel.
- [ ] Instala el **driver del fabricante** (viene en un CD o se descarga con la marca y el modelo de la etiqueta
      de abajo, por ejemplo «Xprinter XP-80 driver»). Usa la opción de **80 mm**.
- [ ] Windows → Configuración → Dispositivos → **Impresoras y escáneres**: debe aparecer. Anota el nombre exacto:
      ____________________.
- [ ] En el programa (como dueña): **Configuración** → «Impresora de tickets» → elige ese nombre → **Imprimir prueba**.
- [ ] Debe pasar: sale un ticket que dice «PRUEBA DE IMPRESORA» con acentos y eñes bien. → **Guardar**.
- [ ] Si no sale nada o sale basura: problema **P1** en «04 · Problemas y soluciones».

## 6. Lector de código de barras (10 min)

- [ ] Conecta el lector por USB (no necesita driver). Abre el Bloc de notas y escanea un repuesto: debe escribir
      el número y **saltar de línea solo**.
- [ ] Si no salta de línea o salen caracteres raros: problema **P2**.

## 7. Pruebas de aceptación en MODO DE PRUEBA (60 min)

- [ ] Cierra el programa normal y abre **«Borealis Repuestos (modo de prueba)»**. Debe verse la **franja amarilla**.
- [ ] Sale su propio asistente: crea una dueña de práctica (usuario `prueba`, clave `prueba123`). En Configuración
      elige la misma impresora.
- [ ] Sigue **«02 · Pruebas en sitio»** criterio por criterio, junto a la dueña, y marca cada uno.
- [ ] Al terminar, cierra el modo de prueba. **Nada de eso aparece en el programa normal.**

## 8. Google Drive y respaldo, en el programa normal (20 min)

- [ ] En Chrome entra a **google.com/drive/download** → «Descargar Drive para computadoras» → instálalo.
- [ ] **La dueña** inicia sesión con su cuenta de Google (ella escribe la clave).
- [ ] Abre el Explorador: aparece **Google Drive (G:)**. Dentro de «Mi unidad» crea la carpeta
      **«Respaldo Romero Alfa 1»**.
- [ ] Programa normal (como dueña) → **Configuración** → «Carpeta de respaldo en la nube» → **Elegir…** → esa carpeta →
      Guardar.
- [ ] **Respaldo** → **Respaldar ahora**. Debe pasar: «En la nube» muestra la fecha y hora de ahora.
- [ ] En el **celular de la dueña**, app Google Drive → carpeta «Respaldo Romero Alfa 1»: aparecen `romero_….db`,
      **«Inventario de hoy.pdf»** y **«Resumen del mes.pdf»** (puede tardar 1 o 2 minutos). Ábrele el resumen.
- [ ] Barra de estado de abajo: «Respaldo en la nube: …» sin color amarillo.

## 9. Tasa BCV y UPS (10 min)

- [ ] Programa normal → **Tasa BCV** → **Descargar del BCV ahora**. Debe pasar: muestra la tasa con «BCV automática».
      Si falla, problema **P5**; mientras tanto la dueña la carga a mano.
- [ ] Conecta la PC, el monitor y la impresora a la **UPS** (la PC no a la pared).

## 10. Capacitación (1 h 45 min)

- [ ] Sigue **«03 · Guion de capacitación»**: sesión 1 con la dueña, sesión 2 con la dueña y el vendedor.
      **Practican en modo de prueba**; al final les muestras que el programa normal está limpio.
- [ ] En el programa normal, la dueña crea el **usuario del vendedor** (Usuarios → Nuevo vendedor). El vendedor
      escribe su propia clave.
- [ ] Pega la **guía rápida** impresa junto a la computadora. Muéstrales Ayuda → Guía rápida (tecla F1).

## 11. Cierre (15 min)

- [ ] Pregunta a la dueña si llevar el **fiado en dólares** le funciona y anota su respuesta en el acta.
- [ ] Llenen y firmen el **acta de entrega** (al final de «02 · Pruebas en sitio»). Tómale **foto**.
- [ ] Borra del escritorio el acceso «(modo de prueba)» si la dueña no lo quiere (sigue en el menú Inicio).
- [ ] Si algo falló: copia la carpeta `C:\ProgramData\BorealisRepuestos\logs` al pendrive para Gabriel.
- [ ] Envía a Gabriel por WhatsApp: foto del acta, los datos de los pasos 2 y 5, y lo que haya quedado pendiente.
- [ ] Acuerda con la dueña el acompañamiento por WhatsApp de la **primera semana**.

## Nunca hagas esto

- Borrar o mover la carpeta `C:\ProgramData\BorealisRepuestos` (ahí están **todos** los datos de la tienda).
- Hacer ventas, compras o fiados de prueba en el programa **normal**.
- **Restaurar** un respaldo en el programa normal (en modo de prueba sí puedes, es parte de las pruebas).
- Escribir o conocer las claves de la dueña o del vendedor.
