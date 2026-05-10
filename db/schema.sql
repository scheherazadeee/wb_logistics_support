
CREATE TABLE IF NOT EXISTS realization_report (
    rrd_id                      BIGINT PRIMARY KEY,
    date_from                   DATE,
    date_to                     DATE,
    nm_id                       BIGINT,
    sa_name                     TEXT,
    ts_name                     TEXT,
    barcode                     TEXT,
    subject_name                TEXT,
    brand_name                  TEXT,
    doc_type_name               TEXT,        -- "Продажа", "Возврат", "Компенсация"
    quantity                    INTEGER,
    retail_price                NUMERIC,
    retail_price_withdisc_rub   NUMERIC,
    ppvz_for_pay                NUMERIC,
    sale_percent                NUMERIC,
    commission_percent          NUMERIC,
    office_name                 TEXT,
    supplier_oper_name          TEXT,
    order_dt                    TIMESTAMP,
    sale_dt                     TIMESTAMP,
    penalty                     NUMERIC,
    additional_payment          NUMERIC,
    srid                        TEXT
);

CREATE INDEX IF NOT EXISTS idx_realization_nm_sale_dt ON realization_report(nm_id, sale_dt);
CREATE INDEX IF NOT EXISTS idx_realization_sale_dt    ON realization_report(sale_dt);


CREATE TABLE IF NOT EXISTS warehouses (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    address           TEXT,
    work_time         TEXT,
    is_active         BOOLEAN,
    is_transit_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS warehouse_remains (
    nm_id          BIGINT,
    volume         NUMERIC,
    warehouse_name TEXT,
    quantity       INTEGER,
    PRIMARY KEY (nm_id, warehouse_name)
);


CREATE TABLE IF NOT EXISTS paid_storage (
    date                 DATE,
    nm_id                BIGINT,
    chrt_id              BIGINT,
    gi_id                BIGINT,
    barcode              TEXT,
    warehouse            TEXT,
    office_id            INTEGER,
    warehouse_coef       NUMERIC,
    log_warehouse_coef   NUMERIC,
    size                 TEXT,
    subject              TEXT,
    brand                TEXT,
    vendor_code          TEXT,
    volume               NUMERIC,
    calc_type            TEXT,
    warehouse_price      NUMERIC,
    barcodes_count       INTEGER,
    pallet_place_code    INTEGER,
    pallet_count         INTEGER,
    original_date        DATE,
    loyalty_discount     NUMERIC,
    tariff_fix_date      DATE,
    tariff_lower_date    DATE,
    PRIMARY KEY (date, chrt_id, warehouse)
);


CREATE TABLE IF NOT EXISTS region_sale (
    nm_id                        BIGINT,
    sa                           TEXT,
    city_name                    TEXT,
    region_name                  TEXT,
    country_name                 TEXT,
    fo_name                      TEXT,
    sale_invoice_cost_price      NUMERIC,
    sale_invoice_cost_price_perc NUMERIC,
    sale_item_invoice_qty        INTEGER
);


CREATE TABLE IF NOT EXISTS supplier_sales (
    sale_id              TEXT PRIMARY KEY,    -- "S..." продажа, "R..." возврат
    date                 TIMESTAMP,
    last_change_date     TIMESTAMP,
    nm_id                BIGINT,
    supplier_article     TEXT,
    barcode              TEXT,
    tech_size            TEXT,
    category             TEXT,
    subject              TEXT,
    brand                TEXT,
    warehouse_name       TEXT,
    country_name         TEXT,
    region_name          TEXT,
    total_price          NUMERIC,             -- цена до скидки
    discount_percent     NUMERIC,
    spp                  NUMERIC,             -- скидка покупателя
    price_with_disc      NUMERIC,             -- финальная цена
    for_pay              NUMERIC,             -- к выплате
    finished_price       NUMERIC,             -- сумма продажи
    is_cancel            BOOLEAN,             -- флаг отмены/возврата
    order_type           TEXT,
    sticker              TEXT,
    g_number             TEXT,
    srid                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_supplier_sales_date_nm ON supplier_sales(date, nm_id);
CREATE INDEX IF NOT EXISTS idx_supplier_sales_nm ON supplier_sales(nm_id);


CREATE TABLE IF NOT EXISTS supplier_orders (
    srid                 TEXT PRIMARY KEY,
    date                 TIMESTAMP,
    last_change_date     TIMESTAMP,
    nm_id                BIGINT,
    supplier_article     TEXT,
    barcode              TEXT,
    tech_size            TEXT,
    category             TEXT,
    subject              TEXT,
    brand                TEXT,
    warehouse_name       TEXT,
    country_name         TEXT,
    region_name          TEXT,
    total_price          NUMERIC,
    discount_percent     NUMERIC,
    spp                  NUMERIC,
    price_with_disc      NUMERIC,
    finished_price       NUMERIC,
    is_cancel            BOOLEAN,
    cancel_date          TIMESTAMP,
    order_type           TEXT,
    sticker              TEXT,
    g_number             TEXT
);

CREATE INDEX IF NOT EXISTS idx_supplier_orders_date_nm ON supplier_orders(date, nm_id);
CREATE INDEX IF NOT EXISTS idx_supplier_orders_nm ON supplier_orders(nm_id);


CREATE TABLE IF NOT EXISTS goods_return (
    srid                  TEXT PRIMARY KEY,
    order_id              BIGINT,
    nm_id                 BIGINT,
    barcode               TEXT,
    brand                 TEXT,
    subject_name          TEXT,
    tech_size             TEXT,
    shk_id                BIGINT,
    sticker_id            TEXT,
    order_dt              TIMESTAMP,
    expired_dt            TIMESTAMP,
    ready_to_return_dt    TIMESTAMP,
    completed_dt          TIMESTAMP,
    return_type           TEXT,
    reason                TEXT,
    status                TEXT,
    is_status_active      BOOLEAN,
    dst_office_id         BIGINT,
    dst_office_address    TEXT
);
