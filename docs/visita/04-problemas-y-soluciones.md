# Problemas y soluciones

Para Josner durante la visita, y para la primera semana de acompañamiento. Si nada de esto lo resuelve: foto de la
pantalla a Gabriel por WhatsApp. **Nunca borres ni muevas `C:\ProgramData\BorealisRepuestos`.**

## P1 · La impresora térmica no imprime o imprime basura

1. ¿Encendida, con papel, tapa cerrada, luz verde? ¿El cable USB va directo a la PC (no a un hub)?
2. Windows → Impresoras y escáneres → la impresora → **Imprimir página de prueba** (de Windows). Si eso tampoco
   imprime, el problema es el driver: reinstala el del fabricante.
3. Si Windows imprime pero el programa no: en Configuración, revisa que el nombre elegido sea **exactamente** el de
   Windows → Imprimir prueba.
4. Si sale basura o caracteres raros: en Windows, propiedades de la impresora, busca una opción tipo
   «ESC/POS», «RAW» o «Generic / Text Only» y elígela. Vuelve a probar.
5. Mientras tanto se puede vender igual: el programa ofrece **Guardar PDF** de cada nota y la venta **no se pierde**.
   Después se reimprime desde Ventas del día.

## P2 · El lector de código de barras no funciona bien

- **No escribe nada:** cambia de puerto USB. Prueba en el Bloc de notas.
- **Escribe el código pero no salta de línea:** el lector debe enviar **Enter** al final. En su manual hay un código de
  barras de configuración «Add CR suffix» / «Enter»: escanéalo.
- **Cambia letras o símbolos** (por ejemplo `'` en vez de `-`): el lector está en otro idioma de teclado. En el
  manual, escanea el código «Latin America» o «Spanish». Los códigos solo numéricos no tienen este problema.

## P3 · «Windows protegió su PC» al instalar

Clic en **Más información** → **Ejecutar de todas formas**. Si el antivirus lo bloquea, permítelo («Permitir en el
dispositivo»). Es normal: el instalador no tiene firma comercial.

## P4 · El programa no abre o se cierra solo

1. Reinicia la PC y vuelve a abrirlo.
2. Si sale un mensaje, tómale foto.
3. Copia la carpeta `C:\ProgramData\BorealisRepuestos\logs` a un pendrive y envíasela a Gabriel.

## P5 · No baja la tasa del BCV

- Sin internet o la página del BCV caída: es normal que pase a veces. **Tasa BCV → Cargar a mano** (la dueña copia
  la tasa del día desde la página del BCV o su banco).
- La barra de abajo se pone **amarilla** si la tasa tiene más de 3 días: hay que cargarla.
- Si nunca baja aunque haya internet: avisa a Gabriel (puede que el BCV cambió su página).

## P6 · «No hay tasa del día» o «La caja está cerrada» al vender

Es a propósito: sin tasa o sin caja abierta no se puede vender. Cargar la tasa (Tasa BCV) o abrir la caja (Caja).

## P7 · El respaldo en la nube no se actualiza (barra amarilla)

1. ¿Google Drive para computadoras está abierto? (ícono de nube abajo a la derecha, junto a la hora). Si no, ábrelo
   desde el menú Inicio y que la dueña inicie sesión.
2. Configuración → «Carpeta de respaldo en la nube»: debe ser la carpeta dentro de `G:\Mi unidad`.
3. Respaldo → **Respaldar ahora**. Mira la hora de «En la nube».
4. El respaldo **local** se hace igual aunque falle la nube: los datos no se pierden.

## P8 · La dueña olvidó su contraseña

**No se puede recuperar desde el programa.** No reinstales ni borres nada. Avisa a Gabriel. (Para el vendedor sí:
la dueña entra y en Usuarios → Restablecer contraseña.)

## P9 · Usuario bloqueado

Después de 5 claves equivocadas, el usuario queda bloqueado **5 minutos**. Esperar y volver a intentar.

## P10 · Aviso «existencias que no cuadran» al abrir

Algo dejó una existencia distinta de la suma de sus movimientos (no debería pasar nunca). No hagas ajustes para
«arreglarlo»: anota los productos que dice, foto, y avisa a Gabriel. El programa sigue funcionando.

## P11 · Se vendió algo por error

- **El mismo día y con la caja abierta:** Ventas del día → Anular venta (el vendedor necesita la clave de la dueña).
- **Si la caja ya se cerró:** ya no se anula. La dueña corrige la existencia en Inventario → Ajuste → «Entrada por
  corrección», con el motivo.

## P12 · La letra se ve muy pequeña

Configuración → marcar **«Letra grande»** → Guardar → cerrar y volver a abrir el programa.

## Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Programa | `C:\Program Files\Borealis Repuestos` |
| **Datos de la tienda (no tocar)** | `C:\ProgramData\BorealisRepuestos\datos\romero.db` |
| Respaldos locales (últimos 30) | `C:\ProgramData\BorealisRepuestos\respaldos` |
| Registro técnico para Gabriel | `C:\ProgramData\BorealisRepuestos\logs` |
| Tickets guardados en PDF | `C:\ProgramData\BorealisRepuestos\tickets` |
| Datos del modo de prueba | `C:\ProgramData\BorealisRepuestos-prueba` |
