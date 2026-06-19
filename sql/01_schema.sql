-- Raw tables
CREATE TABLE IF NOT EXISTS raw_orders (
    order_id                        TEXT PRIMARY KEY,
    customer_id                     TEXT,
    order_status                    TEXT,
    order_purchase_timestamp        TIMESTAMP,
    order_approved_at               TIMESTAMP,
    order_delivered_carrier_date    TIMESTAMP,
    order_delivered_customer_date   TIMESTAMP,
    order_estimated_delivery_date   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_order_items (
    order_id            TEXT,
    order_item_id       INTEGER,
    product_id          TEXT,
    seller_id           TEXT,
    shipping_limit_date TIMESTAMP,
    price               NUMERIC,
    freight_value       NUMERIC
);

CREATE TABLE IF NOT EXISTS raw_products (
    product_id                  TEXT PRIMARY KEY,
    product_category_name       TEXT,
    product_name_lenght         INTEGER,
    product_description_lenght  INTEGER,
    product_photos_qty          INTEGER,
    product_weight_g            INTEGER,
    product_length_cm           INTEGER,
    product_height_cm           INTEGER,
    product_width_cm            INTEGER
);

CREATE TABLE IF NOT EXISTS raw_category_translation (
    product_category_name            TEXT PRIMARY KEY,
    product_category_name_english    TEXT
);

CREATE TABLE IF NOT EXISTS raw_customers (
    customer_id             TEXT PRIMARY KEY,
    customer_unique_id      TEXT,
    customer_zip_code_prefix TEXT,
    customer_city           TEXT,
    customer_state          TEXT
);

-- Fact tables
CREATE TABLE IF NOT EXISTS gmv_fact (
    metric_date     DATE    NOT NULL,
    segment_dim     TEXT    NOT NULL,
    segment_value   TEXT    NOT NULL,
    gmv             NUMERIC NOT NULL,
    order_count     INTEGER NOT NULL,
    PRIMARY KEY (metric_date, segment_dim, segment_value)
);

CREATE TABLE IF NOT EXISTS gmv_total (
    metric_date     DATE    PRIMARY KEY,
    gmv             NUMERIC NOT NULL,
    order_count     INTEGER NOT NULL
);

-- Shock-adjusted copies used by detector/narrator
CREATE TABLE IF NOT EXISTS gmv_fact_shocked (
    metric_date     DATE    NOT NULL,
    segment_dim     TEXT    NOT NULL,
    segment_value   TEXT    NOT NULL,
    gmv             NUMERIC NOT NULL,
    order_count     INTEGER NOT NULL,
    PRIMARY KEY (metric_date, segment_dim, segment_value)
);

CREATE TABLE IF NOT EXISTS gmv_total_shocked (
    metric_date     DATE    PRIMARY KEY,
    gmv             NUMERIC NOT NULL,
    order_count     INTEGER NOT NULL
);
