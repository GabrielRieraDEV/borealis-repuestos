"""Subproceso para la prueba de corte de luz: cobra ventas en bucle hasta que lo matan.

Uso: python tests/powercut_worker.py <ruta.db> <semilla>
"""

from __future__ import annotations

import contextlib
import random
import sys
from decimal import Decimal

from repuestos.db.connection import connect
from repuestos.db.repositories import users as users_repo
from repuestos.domain.sale import PaymentInput, PaymentMethod
from repuestos.services import credit_service, rate_service, sale_service
from repuestos.services.sale_service import CartItem


def main() -> None:
    conn = connect(sys.argv[1])
    rnd = random.Random(int(sys.argv[2]))
    user = users_repo.get(conn, 1)
    assert user is not None
    rate = rate_service.require_rate(conn).rate
    product_ids = [r[0] for r in conn.execute("SELECT id FROM products WHERE active = 1")]
    customer_id = conn.execute("SELECT id FROM customers WHERE credit_enabled = 1").fetchone()[0]
    print("ready", flush=True)
    last_sale_id = None
    while True:
        if last_sale_id is not None and rnd.random() < 0.1:
            with contextlib.suppress(ValueError):  # rechazo esperado: la deuda de esa venta ya tiene abonos
                sale_service.void_sale(conn, user, last_sale_id, "prueba de corte")
            last_sale_id = None
            continue
        roll = rnd.random()
        if roll < 0.1 and credit_service.customer_balance(conn, customer_id) > 1:
            credit_service.register_payment(conn, user, customer_id, PaymentMethod.CASH_USD, Decimal(1))
            continue
        items = [CartItem(pid, Decimal(rnd.randint(1, 3))) for pid in rnd.sample(product_ids, rnd.randint(1, 3))]
        total = sale_service.totals([sale_service.quote_line(conn, i.product_id, i.qty, rate) for i in items]).ves.total
        if roll < 0.3:
            payments = [PaymentInput(PaymentMethod.CASH_VES, Decimal(100))]
            sale = sale_service.charge(conn, user, items, payments, rate, customer_id, on_credit=True)
            last_sale_id = sale.id
            continue
        if rnd.random() < 0.5:
            payments = [PaymentInput(PaymentMethod.POS, total)]
            change = Decimal(0)
        else:
            payments = [PaymentInput(PaymentMethod.CASH_USD, Decimal(500))]
            change = Decimal(rnd.randint(0, 1))
        last_sale_id = sale_service.charge(conn, user, items, payments, rate, change_usd=change).id


if __name__ == "__main__":
    main()
