-- Borealis Repuestos · Romero Alfa 1 · Migración 0001 (esquema inicial)
-- Escalas: _e4 unitario USD ×10.000 · _e2 montos ×100 · _e3 cantidades ×1.000 · _e6 tasa ×1.000.000 · _bp % ×100
-- Fechas y horas: TEXT ISO 8601 en hora local de Caracas ('AAAA-MM-DD' o 'AAAA-MM-DD HH:MM:SS').
-- Ver docs/03-modelo-de-datos.md para invariantes y docs/02-reglas-de-negocio.md para fórmulas.
-- El runner de migraciones abre la transacción, activa foreign_keys y registra la versión en schema_migrations.

CREATE TABLE schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ---------------------------------------------------------------- configuración
CREATE TABLE settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

INSERT INTO settings (key, value) VALUES
    ('business_name',          ''),
    ('business_rif',           ''),
    ('business_address',       ''),
    ('business_phone',         ''),
    ('rounding_multiple_e2',   '500'),     -- 5,00 Bs (RN-03)
    ('default_min_stock_e3',   '10000'),   -- 10 unidades (RN-10)
    ('default_credit_days',    '15'),      -- RN-07
    ('allow_negative_stock',   '0'),       -- RN-09
    ('payment_usdt_enabled',   '0'),       -- RN-06
    ('igtf_bp',                '0'),       -- sin lógica en esta fase
    ('printer_name',           ''),
    ('cloud_backup_dir',       ''),
    ('last_backup_at',         ''),
    ('last_cloud_backup_at',   ''),
    ('large_font',             '0');

-- correlativos sin saltos (RN-12)
CREATE TABLE doc_sequences (
    doc_type     TEXT PRIMARY KEY,               -- 'NE' nota de entrega, 'AB' abono, 'R' código de producto
    next_number  INTEGER NOT NULL CHECK (next_number >= 1)
);
INSERT INTO doc_sequences (doc_type, next_number) VALUES ('NE', 1), ('AB', 1), ('R', 1);

-- ---------------------------------------------------------------- usuarios y bitácora
CREATE TABLE users (
    id               INTEGER PRIMARY KEY,
    username         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name        TEXT NOT NULL,
    role             TEXT NOT NULL CHECK (role IN ('owner', 'seller')),
    password_hash    TEXT NOT NULL,                    -- scrypt, formato 'scrypt$n$r$p$salt_b64$hash_b64'
    active           INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    failed_attempts  INTEGER NOT NULL DEFAULT 0,
    locked_until     TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE audit_log (
    id               INTEGER PRIMARY KEY,
    user_id          INTEGER REFERENCES users(id),
    authorized_by    INTEGER REFERENCES users(id),     -- dueña que autorizó con su clave (RF-04)
    action           TEXT NOT NULL,                    -- p. ej. 'SALE_VOID', 'PRICE_CHANGE', 'LOGIN_FAILED'
    entity           TEXT,
    entity_id        INTEGER,
    details_json     TEXT,                             -- valores antes/después, motivo
    created_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX ix_audit_created ON audit_log(created_at);

-- ---------------------------------------------------------------- catálogo
CREATE TABLE categories (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    active  INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
INSERT INTO categories (name) VALUES
    ('Motor'), ('Frenos'), ('Transmisión y arrastre'), ('Eléctrico'), ('Suspensión'),
    ('Carrocería y plásticos'), ('Cauchos y tripas'), ('Accesorios'), ('Herramientas'), ('Repuestos de carro');

CREATE TABLE products (
    id                 INTEGER PRIMARY KEY,
    code               TEXT NOT NULL UNIQUE,                     -- 'R-00001' (doc_sequences 'R')
    barcode            TEXT UNIQUE,                              -- opcional
    name               TEXT NOT NULL,
    brand              TEXT NOT NULL DEFAULT '',                 -- marca del repuesto
    compatible_models  TEXT NOT NULL DEFAULT '',                 -- "Bera 150, Empire Owen 150"
    category_id        INTEGER REFERENCES categories(id),
    location           TEXT NOT NULL DEFAULT '',                 -- estante
    unit               TEXT NOT NULL DEFAULT 'UNIDAD'
                       CHECK (unit IN ('UNIDAD', 'PAR', 'JUEGO', 'DOCENA', 'METRO', 'LITRO')),
    allows_fraction    INTEGER NOT NULL DEFAULT 0 CHECK (allows_fraction IN (0, 1)),
    cost_usd_e4        INTEGER NOT NULL DEFAULT 0 CHECK (cost_usd_e4 >= 0),   -- costo promedio (RN-08)
    price_usd_e4       INTEGER NOT NULL CHECK (price_usd_e4 >= 0),           -- con IVA (RN-02)
    vat_rate_bp        INTEGER NOT NULL DEFAULT 1600 CHECK (vat_rate_bp >= 0),
    min_stock_e3       INTEGER NOT NULL DEFAULT 10000 CHECK (min_stock_e3 >= 0),
    stock_e3           INTEGER NOT NULL DEFAULT 0,               -- cache; invariante con inventory_movements
    active             INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    search_text        TEXT NOT NULL DEFAULT '',                 -- normalizado: minúsculas, sin acentos (RF-12)
    created_at         TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX ix_products_active ON products(active);
CREATE INDEX ix_products_category ON products(category_id);

-- ---------------------------------------------------------------- tasa
CREATE TABLE exchange_rates (
    id          INTEGER PRIMARY KEY,
    valid_date  TEXT NOT NULL UNIQUE,                 -- fecha valor del BCV (RN-01)
    rate_e6     INTEGER NOT NULL CHECK (rate_e6 > 0),
    source      TEXT NOT NULL CHECK (source IN ('BCV_AUTO', 'MANUAL')),
    user_id     INTEGER REFERENCES users(id),         -- solo MANUAL
    fetched_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ---------------------------------------------------------------- compras
CREATE TABLE suppliers (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    rif     TEXT NOT NULL DEFAULT '',
    phone   TEXT NOT NULL DEFAULT '',
    active  INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE purchases (
    id                INTEGER PRIMARY KEY,
    supplier_id       INTEGER NOT NULL REFERENCES suppliers(id),
    supplier_invoice  TEXT NOT NULL DEFAULT '',
    purchase_date     TEXT NOT NULL,                  -- 'AAAA-MM-DD'
    total_usd_e2      INTEGER NOT NULL CHECK (total_usd_e2 >= 0),
    notes             TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'COMPLETED' CHECK (status IN ('COMPLETED', 'VOIDED')),
    user_id           INTEGER NOT NULL REFERENCES users(id),
    voided_by         INTEGER REFERENCES users(id),
    voided_at         TEXT,
    void_reason       TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX ix_purchases_date ON purchases(purchase_date);

CREATE TABLE purchase_items (
    id                 INTEGER PRIMARY KEY,
    purchase_id        INTEGER NOT NULL REFERENCES purchases(id),
    product_id         INTEGER NOT NULL REFERENCES products(id),
    qty_e3             INTEGER NOT NULL CHECK (qty_e3 > 0),
    unit_cost_usd_e4   INTEGER NOT NULL CHECK (unit_cost_usd_e4 >= 0),
    line_total_usd_e2  INTEGER NOT NULL CHECK (line_total_usd_e2 >= 0)
);
CREATE INDEX ix_purchase_items_product ON purchase_items(product_id);

-- ---------------------------------------------------------------- clientes
CREATE TABLE customers (
    id                   INTEGER PRIMARY KEY,
    name                 TEXT NOT NULL,
    id_doc               TEXT UNIQUE,                       -- cédula o RIF, normalizado 'V12345678'
    phone                TEXT NOT NULL DEFAULT '',
    credit_enabled       INTEGER NOT NULL DEFAULT 0 CHECK (credit_enabled IN (0, 1)),
    credit_limit_usd_e2  INTEGER CHECK (credit_limit_usd_e2 IS NULL OR credit_limit_usd_e2 >= 0),
    credit_days          INTEGER CHECK (credit_days IS NULL OR credit_days > 0),
    active               INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at           TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
INSERT INTO customers (id, name, id_doc, credit_enabled) VALUES (1, 'Consumidor final', NULL, 0);

-- ---------------------------------------------------------------- caja
CREATE TABLE cash_sessions (
    id                 INTEGER PRIMARY KEY,
    status             TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    opened_by          INTEGER NOT NULL REFERENCES users(id),
    opened_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    opening_usd_e2     INTEGER NOT NULL CHECK (opening_usd_e2 >= 0),
    opening_ves_e2     INTEGER NOT NULL CHECK (opening_ves_e2 >= 0),
    closed_by          INTEGER REFERENCES users(id),
    closed_at          TEXT,
    expected_usd_e2    INTEGER,
    expected_ves_e2    INTEGER,
    counted_usd_e2     INTEGER,
    counted_ves_e2     INTEGER,
    notes              TEXT NOT NULL DEFAULT ''
);
-- una sola caja abierta (RN-11)
CREATE UNIQUE INDEX ux_cash_sessions_one_open ON cash_sessions(status) WHERE status = 'OPEN';

CREATE TABLE cash_movements (
    id          INTEGER PRIMARY KEY,
    session_id  INTEGER NOT NULL REFERENCES cash_sessions(id),
    direction   TEXT NOT NULL CHECK (direction IN ('IN', 'OUT')),
    currency    TEXT NOT NULL CHECK (currency IN ('USD', 'VES')),
    amount_e2   INTEGER NOT NULL CHECK (amount_e2 > 0),
    reason      TEXT NOT NULL,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ---------------------------------------------------------------- ventas
CREATE TABLE sales (
    id               INTEGER PRIMARY KEY,
    doc_type         TEXT NOT NULL DEFAULT 'NE' CHECK (doc_type IN ('NE')),   -- 'FAC' en la fase fiscal
    number           INTEGER NOT NULL,
    session_id       INTEGER NOT NULL REFERENCES cash_sessions(id),
    customer_id      INTEGER NOT NULL REFERENCES customers(id),
    user_id          INTEGER NOT NULL REFERENCES users(id),               -- vendedor (P49)
    rate_e6          INTEGER NOT NULL CHECK (rate_e6 > 0),
    total_ves_e2     INTEGER NOT NULL CHECK (total_ves_e2 >= 0),
    base_ves_e2      INTEGER NOT NULL,
    vat_ves_e2       INTEGER NOT NULL,
    total_usd_e2     INTEGER NOT NULL CHECK (total_usd_e2 >= 0),          -- referencia (RN-05)
    base_usd_e2      INTEGER NOT NULL,
    credit_usd_e2    INTEGER NOT NULL DEFAULT 0 CHECK (credit_usd_e2 >= 0), -- parte fiada (RN-07)
    credit_ves_e2    INTEGER NOT NULL DEFAULT 0 CHECK (credit_ves_e2 >= 0), -- la misma parte en Bs, exacta
    status           TEXT NOT NULL DEFAULT 'COMPLETED' CHECK (status IN ('COMPLETED', 'VOIDED')),
    voided_by        INTEGER REFERENCES users(id),
    voided_at        TEXT,
    void_reason      TEXT,
    -- preparados para la facturación fiscal (sin lógica en esta fase, PRD §3.3)
    control_number   TEXT,
    fiscal_status    TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (doc_type, number),
    CHECK (base_ves_e2 + vat_ves_e2 = total_ves_e2)
);
CREATE INDEX ix_sales_created ON sales(created_at);
CREATE INDEX ix_sales_session ON sales(session_id);

CREATE TABLE sale_items (
    id                 INTEGER PRIMARY KEY,
    sale_id            INTEGER NOT NULL REFERENCES sales(id),
    product_id         INTEGER NOT NULL REFERENCES products(id),
    description        TEXT NOT NULL,                                   -- copia del nombre al vender
    qty_e3             INTEGER NOT NULL CHECK (qty_e3 > 0),
    unit_price_usd_e4  INTEGER NOT NULL CHECK (unit_price_usd_e4 >= 0),
    unit_price_ves_e2  INTEGER NOT NULL CHECK (unit_price_ves_e2 >= 0), -- RN-03
    line_total_ves_e2  INTEGER NOT NULL CHECK (line_total_ves_e2 >= 0), -- RN-04
    line_total_usd_e2  INTEGER NOT NULL CHECK (line_total_usd_e2 >= 0),
    unit_cost_usd_e4   INTEGER NOT NULL CHECK (unit_cost_usd_e4 >= 0),  -- costo promedio al vender
    line_cost_usd_e2   INTEGER NOT NULL CHECK (line_cost_usd_e2 >= 0),
    vat_rate_bp        INTEGER NOT NULL
);
CREATE INDEX ix_sale_items_sale ON sale_items(sale_id);
CREATE INDEX ix_sale_items_product ON sale_items(product_id);

-- ---------------------------------------------------------------- fiado
CREATE TABLE receivables (
    id               INTEGER PRIMARY KEY,
    sale_id          INTEGER NOT NULL UNIQUE REFERENCES sales(id),
    customer_id      INTEGER NOT NULL REFERENCES customers(id) CHECK (customer_id <> 1),
    amount_usd_e2    INTEGER NOT NULL CHECK (amount_usd_e2 > 0),
    balance_usd_e2   INTEGER NOT NULL CHECK (balance_usd_e2 >= 0),
    due_date         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'PAID', 'VOIDED')),
    created_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK (balance_usd_e2 <= amount_usd_e2)
);
CREATE INDEX ix_receivables_customer ON receivables(customer_id, status);

CREATE TABLE credit_payments (
    id              INTEGER PRIMARY KEY,
    number          INTEGER NOT NULL UNIQUE,                 -- 'AB-000001'
    customer_id     INTEGER NOT NULL REFERENCES customers(id),
    session_id      INTEGER NOT NULL REFERENCES cash_sessions(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    rate_e6         INTEGER NOT NULL CHECK (rate_e6 > 0),
    amount_usd_e2   INTEGER NOT NULL CHECK (amount_usd_e2 > 0),
    status          TEXT NOT NULL DEFAULT 'COMPLETED' CHECK (status IN ('COMPLETED', 'VOIDED')),
    voided_by       INTEGER REFERENCES users(id),
    voided_at       TEXT,
    void_reason     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE credit_allocations (
    id                 INTEGER PRIMARY KEY,
    credit_payment_id  INTEGER NOT NULL REFERENCES credit_payments(id),
    receivable_id      INTEGER NOT NULL REFERENCES receivables(id),
    amount_usd_e2      INTEGER NOT NULL CHECK (amount_usd_e2 > 0)
);

-- ---------------------------------------------------------------- pagos (ventas y abonos)
CREATE TABLE payments (
    id                 INTEGER PRIMARY KEY,
    session_id         INTEGER NOT NULL REFERENCES cash_sessions(id),
    sale_id            INTEGER REFERENCES sales(id),
    credit_payment_id  INTEGER REFERENCES credit_payments(id),
    method             TEXT NOT NULL CHECK (method IN ('CASH_VES', 'CASH_USD', 'POS', 'MOBILE', 'USDT')),
    currency           TEXT NOT NULL CHECK (currency IN ('USD', 'VES')),
    amount_e2          INTEGER NOT NULL CHECK (amount_e2 <> 0),   -- en su moneda; negativo si es vuelto
    amount_ves_e2      INTEGER NOT NULL,                          -- equivalente en Bs (RN-06)
    is_change          INTEGER NOT NULL DEFAULT 0 CHECK (is_change IN (0, 1)),
    reference          TEXT NOT NULL DEFAULT '',
    voided             INTEGER NOT NULL DEFAULT 0 CHECK (voided IN (0, 1)),
    created_at         TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK ((sale_id IS NULL) <> (credit_payment_id IS NULL)),
    CHECK ((is_change = 1 AND amount_e2 < 0) OR (is_change = 0 AND amount_e2 > 0)),
    CHECK (is_change = 0 OR method IN ('CASH_VES', 'CASH_USD')),
    CHECK ((method IN ('CASH_USD', 'USDT') AND currency = 'USD') OR
           (method IN ('CASH_VES', 'POS', 'MOBILE') AND currency = 'VES'))
);
CREATE INDEX ix_payments_session ON payments(session_id);
CREATE INDEX ix_payments_sale ON payments(sale_id);

-- ---------------------------------------------------------------- inventario
CREATE TABLE inventory_movements (
    id                INTEGER PRIMARY KEY,
    product_id        INTEGER NOT NULL REFERENCES products(id),
    type              TEXT NOT NULL CHECK (type IN (
                        'INITIAL', 'PURCHASE', 'PURCHASE_VOID', 'SALE', 'SALE_VOID',
                        'ADJ_COUNT', 'ADJ_DAMAGE', 'ADJ_MISSING', 'ADJ_INTERNAL_USE', 'ADJ_CORRECTION_IN')),
    qty_e3            INTEGER NOT NULL CHECK (qty_e3 <> 0),       -- con signo (RN-09)
    stock_after_e3    INTEGER NOT NULL,
    unit_cost_usd_e4  INTEGER NOT NULL CHECK (unit_cost_usd_e4 >= 0),  -- costo promedio del momento (RN-13)
    purchase_id       INTEGER REFERENCES purchases(id),
    sale_id           INTEGER REFERENCES sales(id),
    reason            TEXT NOT NULL DEFAULT '',
    user_id           INTEGER NOT NULL REFERENCES users(id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK (
        (type IN ('INITIAL', 'PURCHASE', 'SALE_VOID', 'ADJ_CORRECTION_IN') AND qty_e3 > 0) OR
        (type IN ('PURCHASE_VOID', 'SALE', 'ADJ_DAMAGE', 'ADJ_MISSING', 'ADJ_INTERNAL_USE') AND qty_e3 < 0) OR
        (type = 'ADJ_COUNT')
    ),
    CHECK (type NOT IN ('PURCHASE', 'PURCHASE_VOID') OR purchase_id IS NOT NULL),
    CHECK (type NOT IN ('SALE', 'SALE_VOID') OR sale_id IS NOT NULL)
);
CREATE INDEX ix_movements_product ON inventory_movements(product_id, id);
CREATE INDEX ix_movements_created ON inventory_movements(created_at);

-- ---------------------------------------------------------------- foto mensual (RN-13)
CREATE TABLE monthly_snapshots (
    year_month           TEXT PRIMARY KEY,           -- mes que cierra, 'AAAA-MM'
    inventory_value_usd_e2 INTEGER NOT NULL,
    taken_at             TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

