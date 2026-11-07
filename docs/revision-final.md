# Revisión final · versión 1.0.0

Revisión de todo el proyecto contra `docs/01-PRD.md` y `docs/02-reglas-de-negocio.md`, según el «Prompt de revisión» del
plan. Estado: **✅ cumplido** · **🟡 parcial** · **⏳ se verifica en sitio** (necesita el equipo del local).
Las pruebas están en `tests/` (`pytest -q`: 296 pruebas, incluida la de corte de luz y la de rendimiento).

## Chequeos transversales

| Chequeo | Resultado | Cómo se verifica |
|---|---|---|
| Ningún `float` en dinero (ni en ningún otro lado) | ✅ | `test_inventory.py::test_ningun_float_en_el_codigo` revisa el código con AST; `test_columnas_escaladas_son_enteros` revisa la base |
| Redondeos con modo explícito | ✅ | Solo `hu()` (ROUND_HALF_UP) y `techo()` en `domain/money.py`; búsqueda de `quantize(`/`round(` sin `rounding=`: ninguno. `test_money.py::test_hu_is_half_up_not_half_even` |
| Escrituras fuera de transacción | ✅ | Todas las escrituras están en servicios dentro de `transaction()`; `audit()`, `apply_movement()` y `sequences.take_next()` fallan si no hay transacción abierta |
| SQL en la UI | ✅ | Ningún `execute`/`SELECT`/`UPDATE`/`INSERT` en `src/repuestos/ui/` |
| Costos visibles para el vendedor | ✅ | Ocultos en la UI y negados en el servicio: `test_seller_never_receives_cost`, `test_vendedor_no_ve_costos_ni_ventas_ajenas`, `test_vendedor_solo_sus_ventas_y_sin_reportes_de_costo`, `test_seller_sees_no_cost_and_read_only_ficha` |
| Invariantes 1–8 de `docs/03` | ✅ | `tests/invariants.py`, verificadas tras cada operación y tras 20 cortes bruscos (`test_powercut.py`) |

## Requisitos funcionales

| RF | Estado | Dónde | Prueba |
|---|---|---|---|
| RF-01 login scrypt, bloqueo 5 min | ✅ | `services/auth_service.py`, `domain/passwords.py` | `test_auth.py::test_five_failures_lock_for_five_minutes` |
| RF-02 asistente de primer arranque | ✅ | `services/setup_service.py`, `ui/setup_wizard.py` | `test_setup_creates_owner_and_settings`, `test_setup_validation` |
| RF-03 usuarios | ✅ | `services/user_service.py`, `ui/admin_dialogs.py` | `test_users_settings.py` (crear, desactivar, restablecer) |
| RF-04 autorizar con clave de la dueña | ✅ | `ui/authorize_dialog.py`, `user_service.authorize_owner` | `test_authorize_owner`, `test_vendedor_anula_solo_con_autorizacion` |
| RF-05 bitácora consultable | ✅ | `services/audit_service.py`, `ui/reports_window.py::AuditWindow` | `test_audit_window_filtra` |
| RF-06 configuración | ✅ | `services/settings_service.py` | `test_settings_save_and_audit`, `test_settings_validation` |
| RF-10 ficha de producto | ✅ | `domain/products.py`, `ui/product_dialog.py` | `test_products.py` |
| RF-11 carga rápida Ctrl+Enter | ✅ | `ui/product_dialog.py` | `test_quick_load_with_ctrl_enter_keeps_category_brand_location` |
| RF-12 búsqueda multipalabra < 300 ms | ✅ | `db/repositories/products.py::search` | `test_search_example_from_prd`, `test_search_performance_5000_products`, `test_rnf05_rendimiento` |
| RF-13 precio y costo solo la dueña, con bitácora | ✅ | `product_service.update_product` | `test_price_and_cost_change_audited_before_after` |
| RF-14 categorías | ✅ | `services/category_service.py` | `test_categories_seed_and_crud`, `test_rename_category_updates_search_text` |
| RF-15 desactivar | ✅ | `product_service.set_active` | `test_deactivate_hides_from_search` |
| RF-16 kardex e historial de compras | ✅ | `inventory_service.kardex`, `ui/product_dialog.py` | `test_kardex_e_historial`, `test_product_dialog_history_tabs` |
| RF-20 descarga BCV cada 2 h | ✅ / ⏳ | `services/bcv.py`, `ui/rate.py` | `test_parse_bcv_fixture` (HTML real); descarga real probada en desarrollo, en sitio con su internet |
| RF-21 tasa manual | ✅ | `rate_service.set_manual_rate` | `test_manual_rate_replaces_and_audits_previous` |
| RF-22 tasa en la barra, aviso > 3 días | ✅ | `ui/main_window.py` | `test_stale_after_three_days`, `test_main_window_status_and_alerts` |
| RF-30 compras con costo promedio y empaque | ✅ | `services/purchase_service.py`, `ui/purchases_window.py` | `test_criterio_2_compra_suma_y_promedia`, `test_compra_por_empaque`, `test_purchase_dialog_keyboard_flow` |
| RF-31 anular compra | ✅ | `purchase_service.void_purchase` | `test_anular_compra_resta_y_no_toca_costo`, `test_anular_bloqueada_si_deja_negativo` |
| RF-32 lista de compras con filtros | ✅ | `purchase_service.list_purchases` | `test_lista_de_compras_con_filtros` |
| RF-40 venta resta, compra suma, misma transacción | ✅ | `services/stock.py::apply_movement` | `test_criterio_1_…`, `test_correlativos_sin_huecos_aunque_una_venta_falle` |
| RF-41 ajustes | ✅ | `inventory_service.adjust` | `test_ajustes`, `test_ajuste_validaciones` |
| RF-42 conteo físico | ✅ | `inventory_service.register_count` | `test_conteo_diferencia_positiva_negativa_y_cero`, `test_conteo_es_todo_o_nada` |
| RF-43 alerta de mínimo, «Para pedir» en PDF y ticket | ✅ | `inventory_service.to_order`, `printing/reports.py`, `printing/ticket.py` | `test_para_pedir_criterio_7_y_ultima_compra`, `test_para_pedir_en_ticket`, `test_pdfs_de_reportes` |
| RF-44 verify_stock | ✅ | `tools/verify_stock.py`, `app.py` | `test_verify_stock_detects_and_logs_difference` |
| RF-50 venta con teclado y lector | ✅ / ⏳ | `ui/sale_window.py` | `test_sale_window_keyboard_flow`; lector real en sitio |
| RF-51 cliente por cédula/RIF | ✅ | `services/customer_service.py` | `test_crear_y_buscar_cliente`, `test_normalizar_documento` |
| RF-52 cobro mixto y vuelto | ✅ | `domain/sale.py`, `ui/sale_window.py::PaymentDialog` | `test_criterio_4_pago_mixto_y_vuelto`, `test_payment_dialog_criterio_4_con_teclado` |
| RF-53 anular venta con su caja abierta | ✅ | `sale_service.void_sale` | `test_anular_anula_pagos_y_conserva_numero`, `test_no_se_anula_con_caja_cerrada_ni_dos_veces` |
| RF-54 nota de entrega 80 mm | ✅ / ⏳ | `printing/ticket.py`, `printing/printer.py` | `test_ticket_de_venta`, `test_sin_impresora_lanza_print_error_y_la_venta_queda`; térmica real en sitio (Configuración → Imprimir prueba) |
| RF-55 sin descuentos ni cambio de precio | ✅ | El precio sale siempre del producto (`sale_service.charge`) | `test_copia_precio_y_costo_al_vender` |
| RF-56 ventas del día y reimpresión | ✅ | `ui/sales_list.py` | `test_sales_list_void_by_seller_with_authorization` |
| RF-60 apertura, una sola caja, sigue al reabrir | ✅ | `services/cash_service.py` | `test_una_sola_caja_abierta`, `test_la_caja_sigue_abierta_al_reabrir` |
| RF-61 entradas y salidas | ✅ | `cash_service.add_movement` | `test_entradas_salidas_y_cierre_ciego` |
| RF-62 cierre ciego, ticket y respaldo | ✅ | `cash_service.close_session`, `ui/cash_window.py` | `test_cash_window_seller_blind_close`, `test_ticket_de_cierre_ciego`, `test_main_window_reportes_respaldo_y_cierre_de_caja` |
| RF-63 historial de cierres | ✅ | `cash_service.history` | `test_entradas_salidas_y_cierre_ciego` |
| RF-70 habilitar fiado, límite y plazo | ✅ | `credit_service.set_customer_credit` | `test_plazo_del_cliente`, `test_customer_credit_dialog` |
| RF-71 venta a fiado total o parcial | ✅ | `sale_service.charge(on_credit=True)` | `test_criterio_6_fiado_en_usd_y_abono`, `test_fiado_parcial`, `test_limite_bloquea_salvo_clave_de_la_duena` |
| RF-72 abonos FIFO con comprobante | ✅ | `credit_service.register_payment` | `test_abono_fifo_con_dos_deudas`, `test_nota_de_entrega_con_fiado_y_comprobante_de_abono` |
| RF-73 estado de cuenta y deudores | ✅ | `credit_service.statement/debtors` | `test_vencidas_deudores_y_total`, `test_credit_window_abono_y_estado_de_cuenta` |
| RF-80 ventas del día | ✅ | `report_service.daily_sales` | `test_ventas_del_dia_y_periodo`, `test_vendedor_solo_sus_ventas_…` |
| RF-81 monto vendido por período (no fiscal) | ✅ | `report_service.period_sales` | `test_ventas_del_dia_y_periodo` |
| RF-82 resumen del mes con 12 meses | ✅ | `report_service.month_summary`, `printing/reports.py` | `test_caso_del_resumen_del_mes` (valores exactos del plan) |
| RF-83 inventario valorizado | ✅ | `report_service.valued_inventory` | `test_inventario_valorizado` |
| RF-84 para pedir | ✅ | ver RF-43 | |
| RF-90 respaldo verificado, 30 + 30, al arrancar/cerrar caja/salir | ✅ / ⏳ | `backup/files.py`, `services/backup_service.py`, `ui/backup_ui.py` | `test_respaldo_local_verificado`, `test_rotacion_deja_30`, `test_backup_manager_en_segundo_plano`; Google Drive real en sitio |
| RF-91 restaurar con doble confirmación | ✅ | `backup_service.restore`, `app.py` | `test_restauracion_de_ida_y_vuelta`, `test_backup_dialog_doble_confirmacion` |
| RF-92 PDF en la nube | ✅ | `print_service.cloud_pdfs` | `test_respaldo_en_la_nube_con_pdfs` |

## Reglas de negocio

| RN | Estado | Dónde | Prueba |
|---|---|---|---|
| RN-01 tasa vigente por fecha valor | ✅ | `rate_service.current_rate` | `test_future_value_date_is_not_current_yet`, `test_only_future_rate_means_no_rate` |
| RN-02 precio en USD con IVA, una lista | ✅ | `domain/products.py` | `test_products.py` |
| RN-03 precio Bs con TECHO | ✅ | `domain/pricing.py::unit_price_ves` | `test_rn03_*`, `test_criterio_3_precio_en_bs` |
| RN-04 renglón | ✅ | `pricing.line_totals` | `test_rn04_*` |
| RN-05 base e IVA sobre el total | ✅ | `pricing.document_totals` | `test_rn05_*` |
| RN-06 pagos y vuelto | ✅ | `domain/sale.py::payment_rows` | `test_rn06_*`, `test_vuelto_que_excede_se_rechaza` |
| RN-07 fiado en USD, límite, abonos FIFO | ✅ | `domain/credit.py`, `credit_service` | `test_rn07_*`, `test_credit.py` |
| RN-08 costo promedio | ✅ | `pricing.weighted_average_cost` | `test_rn08_*`, `test_mismo_producto_dos_veces_aplica_promedio_dos_veces` |
| RN-09 existencias y negativos | ✅ | `services/stock.py`, `sale_service.charge` | `test_existencia_insuficiente_*`, `test_existencia_negativa_permitida_por_configuracion` |
| RN-10 mínimo y para pedir | ✅ | `inventory_repo.to_order` | `test_para_pedir_criterio_7_y_ultima_compra` |
| RN-11 caja | ✅ | `domain/cash.py`, `cash_service` | `test_criterio_5_caja_cuadra`, `test_abonos_en_efectivo_entran_al_arqueo` |
| RN-12 correlativos y nota de entrega | ✅ | `db/repositories/sequences.py`, `printing/ticket.py` | `test_correlativos_sin_huecos_aunque_una_venta_falle`, `test_ticket_de_venta` |
| RN-13 resumen del mes y foto mensual | ✅ | `db/repositories/reports.py`, `report_service` | `test_caso_del_resumen_del_mes`, `test_foto_mensual`, `test_faltantes_de_conteo_aparte` |
| RN-14 anulaciones | ✅ | `sale_service.void_sale`, `purchase_service.void_purchase`, `credit_service.void_payment` | `test_anular_*`, `test_venta_con_abonos_no_se_anula` |
| RN-15 respaldo | ✅ | `backup/files.py` | `test_verificacion_detecta_archivo_danado`, `test_si_falla_la_nube_el_respaldo_local_queda` |
| RN-16 bitácora | ✅ | `services/audit_service.py` (todas las acciones de la lista) | `test_*audit*`, `test_existencia_insuficiente_con_clave_de_la_duena` (registra quién autorizó) |

## Requisitos no funcionales

| RNF | Estado | Evidencia |
|---|---|---|
| RNF-01 sin licencia que caduque | ✅ | No hay activación, verificación en línea ni fechas de vencimiento en el código |
| RNF-02 funciona sin internet | ✅ / ⏳ | Internet solo en `services/bcv.py`; si falla, se carga la tasa a mano. Criterio 9 en sitio |
| RNF-03 cortes de luz | ✅ | WAL + `synchronous=FULL` (`test_pragmas`); `test_corte_de_luz_20_veces` (20/20, con ventas, fiado, abonos y anulaciones) |
| RNF-04 Windows 10/11 64 bits, 1366×768, letra grande | ✅ / ⏳ | Pantallas revisadas a 1366×768 con letra grande. La PC del local tiene Windows 10 (foto) y monitor Samsung SyncMaster de 1440×900; falta confirmar 64 bits en sitio (PRD P1) |
| RNF-05 rendimiento con 5.000 productos y 50.000 ventas | ✅ | `test_rnf05_rendimiento`: arranque 0,4 s · búsqueda 6 ms · venta 3 ms · reportes 0,8 s |
| RNF-06 datos en ProgramData, el instalador no los toca | ✅ / ⏳ | `installer/repuestos.iss` (`uninsneveruninstall`, sin archivos en esa carpeta). Prueba de actualización en sitio (lista A) |
| RNF-07 log rotativo sin datos personales | ✅ | `logging_setup.py` (5 × 1 MB); el log no registra clientes, montos de clientes ni contraseñas |
| RNF-08 español de Venezuela y formatos | ✅ | `formatting.py` (`test_format_amounts`, `test_format_date`); mensajes técnicos reemplazados por indicaciones |
| RNF-09 pruebas automáticas de todas las reglas | ✅ | 296 pruebas |

## Lo que queda para la visita

1. Versión de Windows de la PC Samsung (P1), impresora térmica real, lector real, Google Drive real (P5).
2. Actualizar sobre la versión preliminar y comprobar que los datos se conservan (lista de pruebas en sitio, A).
3. Recorrer los 12 criterios con la dueña (`docs/visita/02-pruebas-en-sitio.md`) y confirmar el fiado en USD (P4).
