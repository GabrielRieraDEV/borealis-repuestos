"""Prueba de humo de la interfaz con teclado simulado (sin pantalla: QT_QPA_PLATFORM=offscreen)."""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal as D

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from repuestos.services import product_service, rate_service  # noqa: E402
from repuestos.ui.admin_dialogs import CategoriesDialog, SettingsDialog, UsersDialog  # noqa: E402
from repuestos.ui.main_window import MainWindow  # noqa: E402
from repuestos.ui.product_dialog import ProductDialog  # noqa: E402
from repuestos.ui.products_window import ProductsWindow  # noqa: E402
from repuestos.ui.rate import BcvFetcher, RateDialog  # noqa: E402
from tests.helpers import make_seller, pastillas  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _type(widget, text: str) -> None:
    """Teclea texto ASCII. (QTest.keyClicks tumba el proceso en Windows con 'é' o '—': esos van con setText.)"""
    widget.setFocus()
    if text.isascii():
        QTest.keyClicks(widget, text)
    else:
        widget.setText(text)


def _show(window) -> None:
    """Sin ventana activa no hay foco ni atajos de teclado."""
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)


def test_quick_load_with_ctrl_enter_keeps_category_brand_location(app, conn: sqlite3.Connection, owner) -> None:
    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    d = ProductDialog(conn, owner)
    _show(d)
    _type(d.name, "Pastillas de freno delanteras — Bera 150")
    QTest.keyClick(d.name, Qt.Key.Key_Return)  # Enter pasa al código de barras, no guarda
    assert d.isVisible() and d.barcode.hasFocus()
    QTest.keyClicks(d.barcode, "7591111")
    QTest.keyClick(d.barcode, Qt.Key.Key_Return)  # el lector termina en Enter
    assert d.isVisible()
    _type(d.brand, "Genérica")
    d.category.setCurrentIndex(d.category.findText("Frenos"))
    _type(d.location, "A-3")
    _type(d.price, "12,50")
    assert d.price_ves.text().endswith("Bs 2.890,00")
    _type(d.cost, "7")
    _type(d.initial_stock, "10")
    QTest.keyClick(d.initial_stock, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)

    assert d.isVisible()
    assert d.status.text().startswith("Guardado R-00001")
    assert (d.name.text(), d.barcode.text(), d.price.text()) == ("", "", "")
    assert (d.brand.text(), d.location.text(), d.category.currentText()) == ("Genérica", "A-3", "Frenos")
    assert d.name.hasFocus()

    _type(d.name, "Pastillas traseras")
    _type(d.price, "10")
    QTest.keyClick(d.price, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    d.close()

    found = product_service.search(conn, owner, "pastilla bera 150")
    assert [p.code for p in found] == ["R-00001"]
    assert found[0].stock == D("10") and found[0].brand == "Genérica"
    assert product_service.search(conn, owner, "traseras")[0].category_name == "Frenos"


def test_products_window_live_search_and_scan(app, conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, pastillas(conn, barcode="7591111"), D("9"))
    product_service.create_product(conn, owner, pastillas(conn, name="Bujía NGK", compatible_models="GN 125"))
    w = ProductsWindow(conn, owner)
    _show(w)
    assert len(w.model.rows) == 2
    _type(w.search, "bera pastilla")
    w.refresh()
    assert [r.name for r in w.model.rows] == ["Pastillas de freno delanteras — Bera 150"]
    assert "pedir" in w.model.data(w.model.index(0, 6))  # existencia 9 <= mínimo 10
    assert "Costo USD" in w.model.columns
    w.close()


def test_seller_sees_no_cost_and_read_only_ficha(app, conn: sqlite3.Connection, owner) -> None:
    p = product_service.create_product(conn, owner, pastillas(conn))
    seller = make_seller(conn, owner)
    w = ProductsWindow(conn, seller)
    assert "Costo USD" not in w.model.columns
    assert not w.new_button.isVisible()
    d = ProductDialog(conn, seller, p.id)
    assert d.cost.text() == ""
    assert d.cost.isHidden() and d.save_button.isHidden()
    assert d.price.isReadOnly()


def test_admin_dialogs_open(app, conn: sqlite3.Connection, owner) -> None:
    for dialog in (CategoriesDialog(conn, owner), UsersDialog(conn, owner), SettingsDialog(conn, owner)):
        dialog.show()
        dialog.close()
    fetcher = BcvFetcher(conn)
    r = RateDialog(conn, owner, fetcher)
    r.show()
    r.manual.setText("240,00")
    r._save_manual()
    assert rate_service.current_rate(conn).rate == D("240.00")
    r.accept()


def test_main_window_status_and_alerts(app, conn: sqlite3.Connection, owner) -> None:
    product_service.create_product(conn, owner, pastillas(conn), D("9"))
    m = MainWindow(conn, owner)
    m.fetcher.start = lambda: None  # sin red en las pruebas
    assert m.rate_label.text() == "Tasa: sin tasa"
    assert "Para pedir: <b>1</b>" in m.alerts.text()
    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    m.refresh_status()
    assert m.rate_label.text().startswith("Tasa: 231,0468")
    assert m.cash_label.text() == "Caja: cerrada"
    m.close()


# ------------------------------------------------------------------ Fase 2


@pytest.fixture
def no_dialogs(monkeypatch):
    """Las preguntas modales se responden «Sí» y los avisos se registran sin bloquear la prueba."""
    shown: list[str] = []
    yes = QtWidgets.QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: yes)
    for name in ("information", "warning"):
        monkeypatch.setattr(QtWidgets.QMessageBox, name, lambda _p, _t, text, *a, **k: shown.append(text))
    return shown


def test_purchase_dialog_keyboard_flow(app, conn: sqlite3.Connection, owner, no_dialogs) -> None:
    from repuestos.services import purchase_service
    from repuestos.ui.purchases_window import PurchaseDialog

    p = product_service.create_product(conn, owner, pastillas(conn, cost_usd=D("10"), barcode="7591111"), D("7"))
    sup = purchase_service.create_supplier(conn, owner, "Distribuidora")
    d = PurchaseDialog(conn, owner)
    _show(d)
    d.supplier.setCurrentIndex(d.supplier.findData(sup.id))
    _type(d.invoice, "F-001")
    _type(d.product_input, "7591111")  # el lector escribe el código y Enter
    QTest.keyClick(d.product_input, Qt.Key.Key_Return)
    assert d.qty.hasFocus() and d.cost.text() == "10,00"  # propone el costo promedio
    QTest.keyClicks(d.qty, "3")
    QTest.keyClick(d.qty, Qt.Key.Key_Return)
    assert d.cost.hasFocus()
    d.cost.selectAll()
    QTest.keyClicks(d.cost, "12")
    QTest.keyClick(d.cost, Qt.Key.Key_Return)
    assert len(d.lines) == 1 and d.product_input.hasFocus()
    assert d.total_label.text() == "Total: USD 36,00"
    QTest.keyClick(d, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert d.saved_id is not None, no_dialogs
    view = product_service.get_view(conn, owner, p.id)
    assert (view.stock, view.cost_usd) == (D("10"), D("10.6000"))  # criterio 2 por la interfaz


def test_purchase_dialog_requires_supplier(app, conn: sqlite3.Connection, owner, no_dialogs) -> None:
    from repuestos.ui.purchases_window import PurchaseDialog

    product_service.create_product(conn, owner, pastillas(conn, barcode="7591111"))
    d = PurchaseDialog(conn, owner)
    _show(d)
    d._choose_product("7591111")
    d.qty.setText("1")
    d.cost.setText("1")
    d._add_line()
    d._save()
    assert d.saved_id is None and "proveedor" in no_dialogs[-1]


def test_pack_dialog(app) -> None:
    from repuestos.ui.purchases_window import PackDialog

    d = PackDialog()
    d.packs.setText("2")
    d.units.setText("12")
    d.pack_cost.setText("18")
    assert "24 unidades a USD 1,5000" in d.preview.text()
    d._accept()
    assert (d.result_qty, d.result_cost) == (D("24"), D("1.5000"))


def test_inventory_window_adjust_count_and_to_order(app, conn: sqlite3.Connection, owner, no_dialogs) -> None:
    from repuestos.ui.inventory_window import InventoryWindow

    a = product_service.create_product(conn, owner, pastillas(conn, location="A-3"), D("11"))
    b = product_service.create_product(conn, owner, pastillas(conn, name="Cadena 428", location="A-3"), D("5"))
    w = InventoryWindow(conn, owner)
    _show(w)
    assert w.to_order.table.rowCount() == 1  # Cadena: 5 <= mínimo 10

    adj = w.tabs.widget(1)
    _type(adj.product_input, "R-00001")
    QTest.keyClick(adj.product_input, Qt.Key.Key_Return)
    adj.kind.setCurrentIndex(adj.kind.findData("DAMAGE"))
    adj.qty.setText("1")
    adj.reason.setText("golpe")
    adj._save()
    assert "11 → 10" in adj.result.text()

    count = w.count
    count.location.setCurrentIndex(count.location.findData("A-3"))
    count.load()
    assert [r.code for r in count.rows] == ["R-00002", "R-00001"]  # Cadena, Pastillas
    count.table.item(0, count.COL_COUNTED).setText("6")
    count.table.item(1, count.COL_COUNTED).setText("10")
    assert count.table.item(0, count.COL_DIFF).text() == "+1"
    assert count.table.item(1, count.COL_DIFF).text() == "cuadra"
    count._save()
    assert "1 ajustados" in no_dialogs[-1]
    assert product_service.get_view(conn, owner, b.id).stock == D("6")
    assert product_service.get_view(conn, owner, a.id).stock == D("10")


def test_product_dialog_history_tabs(app, conn: sqlite3.Connection, owner) -> None:
    from repuestos.domain.inventory import AdjustmentKind
    from repuestos.services import inventory_service

    p = product_service.create_product(conn, owner, pastillas(conn), D("10"))
    inventory_service.adjust(conn, owner, p.id, AdjustmentKind.DAMAGE, D("1"), "golpe")
    d = ProductDialog(conn, owner, p.id)
    assert d.tabs is not None and d.tabs.count() == 3
    assert d.kardex_table.rowCount() == 2
    assert d.kardex_table.item(0, 1).text() == "Dañado"
    assert d.kardex_table.item(0, 6).text() == "golpe"
    seller = make_seller(conn, owner)
    assert ProductDialog(conn, seller, p.id).tabs is None  # el vendedor no ve kardex con costos


def test_main_window_buttons_by_role(app, conn: sqlite3.Connection, owner) -> None:
    texts = lambda w: {b.text() for b in w.findChildren(QtWidgets.QPushButton) if b.isEnabled()}  # noqa: E731
    m = MainWindow(conn, owner)
    m.fetcher.start = lambda: None
    assert {"Compras", "Inventario", "Configuración"} <= texts(m)
    seller = make_seller(conn, owner)
    s = MainWindow(conn, seller)
    s.fetcher.start = lambda: None
    assert not ({"Compras", "Inventario", "Configuración", "Usuarios"} & texts(s))
    m.close()
    s.close()


# ------------------------------------------------------------------ Fase 3


@pytest.fixture
def open_shop(conn: sqlite3.Connection, owner):
    from repuestos.domain.products import ProductData, Unit
    from repuestos.services import cash_service

    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    a = product_service.create_product(conn, owner, pastillas(conn, barcode="7591111"), D("10"))
    b = product_service.create_product(
        conn,
        owner,
        ProductData(name="Cable electrico", unit=Unit.METRO, allows_fraction=True, price_usd=D("0.80")),
        D("100"),
    )
    cash_service.open_session(conn, owner, D("20"), D("500"))
    return a, b


class _FakePayment:
    """Reemplaza el diálogo de cobro (modal) por pagos fijos."""

    payments: list = []
    change_usd = D("0")

    def __init__(self, *args, **kwargs) -> None:
        pass

    def exec(self):
        return QtWidgets.QDialog.DialogCode.Accepted


def test_sale_window_keyboard_flow(app, conn, owner, open_shop, monkeypatch, no_dialogs) -> None:
    import repuestos.ui.sale_window as sw
    from repuestos.domain.sale import PaymentInput, PaymentMethod

    a, b = open_shop
    printed: list = []
    monkeypatch.setattr(sw, "print_with_fallback", lambda *args: printed.append(args) or True)
    w = sw.SaleWindow(conn, owner)
    _show(w)
    w.qty.setText("2")
    _type(w.search, "7591111")  # el lector escribe el código y Enter: agrega directo con la cantidad
    QTest.keyClick(w.search, Qt.Key.Key_Return)
    assert [(q.code, q.qty) for q in w.lines] == [("R-00001", D("2"))]
    assert w.search.hasFocus() and w.qty.text() == "1"
    _type(w.search, "cable")  # una sola coincidencia: pasa a la cantidad
    QTest.keyClick(w.search, Qt.Key.Key_Return)
    assert w.qty.hasFocus()
    w.qty.selectAll()
    QTest.keyClicks(w.qty, "2,5")
    QTest.keyClick(w.qty, Qt.Key.Key_Return)
    assert [q.line_total_ves for q in w.lines] == [D("5780.00"), D("462.50")]
    assert w.total_label.text() == "TOTAL Bs 6.242,50"
    QTest.keyClick(w.search, Qt.Key.Key_Delete)  # Supr con la búsqueda vacía quita el renglón elegido
    assert [q.code for q in w.lines] == ["R-00001"]

    _FakePayment.payments = [PaymentInput(PaymentMethod.CASH_USD, D("30"))]  # Bs 6.931,40
    _FakePayment.change_usd = D("4")  # vuelto Bs 1.151,40 = 4 USD (924,19) + Bs 227,21
    monkeypatch.setattr(sw, "PaymentDialog", _FakePayment)
    QTest.keyClick(w, Qt.Key.Key_F9)
    assert w.lines == [], no_dialogs
    assert w.last_label.text().startswith("Última venta NE-000001 · Bs 5.780,00 · vuelto USD 4,00 + Bs 227,21")
    assert len(printed) == 1
    assert product_service.get_view(conn, owner, a.id).stock == D("8")
    assert w.customer.name == "Consumidor final"


def test_payment_dialog_criterio_4_con_teclado(app) -> None:
    from repuestos.domain.sale import PaymentMethod
    from repuestos.ui.sale_window import PaymentDialog

    d = PaymentDialog(D("2890.00"), D("12.50"), D("231.0468"), usdt_enabled=False)
    _show(d)
    assert d.method.findData("USDT") == -1
    credit = d.method.model().item(d.method.findData("CREDIT"))
    assert not credit.isEnabled()
    QTest.keyClick(d, Qt.Key.Key_F2)  # Efectivo USD
    QTest.keyClicks(d.amount, "15")
    QTest.keyClick(d.amount, Qt.Key.Key_Return)
    assert d.change_usd_input.hasFocus() and "Vuelto: Bs 575,70" in d.change_total.text()
    d.change_usd_input.selectAll()
    QTest.keyClicks(d.change_usd_input, "2")
    assert d.change_rest.text().endswith("Bs 113,61")
    d.change_usd_input.selectAll()
    QTest.keyClicks(d.change_usd_input, "3")
    assert not d.charge_button.isEnabled()  # da de más
    d.change_usd_input.selectAll()
    QTest.keyClicks(d.change_usd_input, "2")
    QTest.keyClick(d, Qt.Key.Key_F9)
    assert d.result() == QtWidgets.QDialog.DialogCode.Accepted
    assert [(p.method, p.amount) for p in d.payments] == [(PaymentMethod.CASH_USD, D("15"))]
    assert d.change_usd == D("2")


def test_payment_dialog_enter_vacio_completa(app) -> None:
    from repuestos.ui.sale_window import PaymentDialog

    d = PaymentDialog(D("2890.00"), D("12.50"), D("231.0468"), usdt_enabled=True)
    _show(d)
    QTest.keyClick(d, Qt.Key.Key_F3)  # Punto de venta
    QTest.keyClicks(d.amount, "1000")
    QTest.keyClick(d.amount, Qt.Key.Key_Return)
    assert d.due_label.text().startswith("Falta: Bs 1.890,00")
    QTest.keyClick(d, Qt.Key.Key_F1)
    QTest.keyClick(d.amount, Qt.Key.Key_Return)  # vacío: completa lo que falta
    assert d.summary().complete and d.summary().change_ves == 0
    QTest.keyClick(d.amount, Qt.Key.Key_Return)  # vacío y completo: cobra
    assert d.result() == QtWidgets.QDialog.DialogCode.Accepted


def test_sale_window_sin_existencia_pide_clave(app, conn, owner, open_shop, monkeypatch, no_dialogs) -> None:
    import repuestos.ui.sale_window as sw
    from repuestos.domain.sale import PaymentInput, PaymentMethod

    seller = make_seller(conn, owner)
    monkeypatch.setattr(sw, "print_with_fallback", lambda *args: True)
    asked: list = []
    monkeypatch.setattr(sw, "ask_owner_authorization", lambda *args: asked.append(args) or owner.id)
    _FakePayment.payments = [PaymentInput(PaymentMethod.POS, D("40000"))]
    _FakePayment.change_usd = D("0")
    monkeypatch.setattr(sw, "PaymentDialog", _FakePayment)
    w = sw.SaleWindow(conn, seller)
    _show(w)
    w.qty.setText("12")
    _type(w.search, "7591111")
    QTest.keyClick(w.search, Qt.Key.Key_Return)
    assert "clave de la dueña" in w.selected_label.text()
    w._charge()
    assert len(asked) == 1 and w.last_label.text().startswith("Última venta NE-000001")
    assert product_service.get_view(conn, owner, open_shop[0].id).stock == D("-2")


def test_cash_window_seller_blind_close(app, conn, owner, monkeypatch, no_dialogs) -> None:
    import repuestos.ui.cash_window as cw
    from repuestos.services import cash_service

    seller = make_seller(conn, owner)
    monkeypatch.setattr(cw, "print_with_fallback", lambda *args: True)
    w = cw.CashWindow(conn, seller)
    assert w.tabs.count() == 1  # sin historial para el vendedor
    w.opening_usd.setText("20")
    w.opening_ves.setText("500")
    w._open()
    assert cash_service.current_session(conn) is not None and w.expected.text() == ""
    w.mv_amount.setText("100")
    w.mv_reason.setText("Agua")
    w._movement()
    assert w.movements.rowCount() == 1

    class FakeClose:
        def __init__(self, *a):
            self.values = (D("20"), D("390"))
            self.notes = QtWidgets.QLineEdit()

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted

    monkeypatch.setattr(cw, "CloseDialog", FakeClose)
    w._close()
    assert no_dialogs[-1] == "Cierre registrado."
    assert cash_service.current_session(conn) is None
    owner_window = cw.CashWindow(conn, owner)
    assert owner_window.history.rowCount() == 1
    assert owner_window.history.item(0, 8).text() == "Bs -10,00"


def test_sales_list_void_by_seller_with_authorization(app, conn, owner, open_shop, monkeypatch) -> None:
    import repuestos.ui.sales_list as sl
    from repuestos.domain.sale import PaymentInput, PaymentMethod
    from repuestos.services import sale_service
    from repuestos.services.sale_service import CartItem

    seller = make_seller(conn, owner)
    sale = sale_service.charge(
        conn, seller, [CartItem(open_shop[0].id, D("1"))], [PaymentInput(PaymentMethod.POS, D("2890"))], D("231.0468")
    )
    monkeypatch.setattr(sl.QInputDialog, "getText", lambda *a, **k: ("se equivoco", True))
    monkeypatch.setattr(sl, "ask_owner_authorization", lambda *a: owner.id)
    w = sl.SalesListWindow(conn, seller)
    assert w.table.rowCount() == 1
    w.table.selectRow(0)
    w._void()
    assert sale_service.get_sale(conn, seller, sale.id).voided
    assert w.table.item(0, 6).text() == "ANULADA"


def test_main_window_blocks_sale_without_cash(app, conn, owner, no_dialogs) -> None:
    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    m = MainWindow(conn, owner)
    m.fetcher.start = lambda: None
    m.open_sale()
    assert "caja está cerrada" in no_dialogs[-1].lower()
    assert m.cash_label.text() == "Caja: cerrada"
    m.close()
