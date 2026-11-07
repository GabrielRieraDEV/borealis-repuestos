"""Marca de Borealis en el sistema y modo de prueba (base aparte para la visita y para practicar)."""

from __future__ import annotations

import os
from decimal import Decimal as D

import pytest

from repuestos import config
from repuestos.domain.sale import PaymentInput, PaymentMethod
from repuestos.services import cash_service, print_service, product_service, rate_service, sale_service
from repuestos.services.sale_service import CartItem
from tests.helpers import pastillas

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def sale(conn, owner):
    rate_service.set_manual_rate(conn, owner, D("231.0468"))
    p = product_service.create_product(conn, owner, pastillas(conn), D("5"))
    cash_service.open_session(conn, owner, D("0"), D("0"))
    return sale_service.charge(
        conn, owner, [CartItem(p.id, D("1"))], [PaymentInput(PaymentMethod.POS, D("2890"))], D("231.0468")
    )


def test_marca_en_tickets(conn, owner, sale) -> None:
    lines = print_service.sale_lines(conn, owner, sale.id)
    assert lines[-1].strip() == "Sistema hecho por Borealis Software Solutions"
    assert "MODO DE PRUEBA" not in "\n".join(lines)
    cash_service.close_session(conn, owner, D("0"), D("0"))
    assert print_service.close_lines(conn, owner, sale.session_id)[-1].strip() == config.BRAND_LINE


def test_marca_en_login_y_pantalla_principal(app, conn, owner) -> None:
    from repuestos.ui.login import LoginDialog
    from repuestos.ui.main_window import MainWindow

    def texts(w):
        return [label.text() for label in w.findChildren(QtWidgets.QLabel)]

    login = LoginDialog(conn, "Romero")
    assert config.BRAND_LINE in texts(login)
    m = MainWindow(conn, owner)
    m.fetcher.start = lambda: None
    assert config.BRAND_LINE in texts(m)
    assert not any("MODO DE PRUEBA" in t for t in texts(m))
    m.close()


def test_modo_de_prueba_usa_otra_carpeta(monkeypatch) -> None:
    monkeypatch.delenv(config.ENV_DATA_DIR, raising=False)
    monkeypatch.delenv(config.ENV_TEST_MODE, raising=False)
    monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
    assert not config.is_test_mode()
    real = config.get_paths().base
    config.enable_test_mode()
    try:
        assert config.is_test_mode()
        assert config.get_paths().base.name == "BorealisRepuestos-prueba"
        assert config.get_paths().base != real
    finally:
        os.environ.pop(config.ENV_TEST_MODE, None)
        os.environ.pop(config.ENV_DATA_DIR, None)


def test_modo_de_prueba_se_ve_en_ticket_y_pantallas(app, conn, owner, sale, monkeypatch) -> None:
    from repuestos.ui.login import LoginDialog
    from repuestos.ui.main_window import MainWindow

    monkeypatch.setenv(config.ENV_TEST_MODE, "1")
    assert print_service.sale_lines(conn, owner, sale.id)[0].strip() == "*** MODO DE PRUEBA - SIN VALIDEZ ***"
    m = MainWindow(conn, owner)
    m.fetcher.start = lambda: None
    assert m.windowTitle().startswith("MODO DE PRUEBA")
    assert any("MODO DE PRUEBA" in label.text() for label in m.findChildren(QtWidgets.QLabel))
    login = LoginDialog(conn, "R")
    assert any("MODO DE PRUEBA" in label.text() for label in login.findChildren(QtWidgets.QLabel))
    m.close()
