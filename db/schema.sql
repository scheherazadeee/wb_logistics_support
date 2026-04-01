
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


CREATE TABLE IF NOT EXISTS goods_return (
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
