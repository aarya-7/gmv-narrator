-- Truncate and rebuild gmv_fact and gmv_total from raw tables.
-- Run after ingest.py loads the CSVs.

TRUNCATE gmv_fact;
TRUNCATE gmv_total;

-- ── Category dimension ────────────────────────────────────────────────────────
WITH top_cats AS (
    -- identify the top N categories by total GMV to bucket the long tail
    SELECT
        COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') AS category,
        SUM(oi.price) AS total_gmv
    FROM raw_order_items oi
    JOIN raw_orders o ON oi.order_id = o.order_id
    JOIN raw_products p ON oi.product_id = p.product_id
    LEFT JOIN raw_category_translation ct
           ON p.product_category_name = ct.product_category_name
    WHERE o.order_status IN ('delivered','shipped','invoiced')
      AND o.order_purchase_timestamp::date BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY 1
    ORDER BY 2 DESC
    LIMIT 20
),
daily_cat AS (
    SELECT
        o.order_purchase_timestamp::date AS metric_date,
        CASE
            WHEN tc.category IS NOT NULL THEN tc.category
            ELSE 'Other'
        END AS segment_value,
        SUM(oi.price)       AS gmv,
        COUNT(DISTINCT o.order_id) AS order_count
    FROM raw_order_items oi
    JOIN raw_orders o ON oi.order_id = o.order_id
    JOIN raw_products p ON oi.product_id = p.product_id
    LEFT JOIN raw_category_translation ct
           ON p.product_category_name = ct.product_category_name
    LEFT JOIN top_cats tc
           ON COALESCE(ct.product_category_name_english, p.product_category_name, 'unknown') = tc.category
    WHERE o.order_status IN ('delivered','shipped','invoiced')
      AND o.order_purchase_timestamp::date BETWEEN '2017-01-01' AND '2018-08-31'
    GROUP BY 1, 2
)
INSERT INTO gmv_fact (metric_date, segment_dim, segment_value, gmv, order_count)
SELECT metric_date, 'category', segment_value, SUM(gmv), SUM(order_count)
FROM daily_cat
GROUP BY 1, 3;

-- ── Region dimension ──────────────────────────────────────────────────────────
WITH state_map(state, region) AS (
    VALUES
    ('AC','North'),('AM','North'),('AP','North'),('PA','North'),
    ('RO','North'),('RR','North'),('TO','North'),
    ('AL','Northeast'),('BA','Northeast'),('CE','Northeast'),
    ('MA','Northeast'),('PB','Northeast'),('PE','Northeast'),
    ('PI','Northeast'),('RN','Northeast'),('SE','Northeast'),
    ('DF','Center-West'),('GO','Center-West'),('MS','Center-West'),('MT','Center-West'),
    ('ES','Southeast'),('MG','Southeast'),('RJ','Southeast'),('SP','Southeast'),
    ('PR','South'),('RS','South'),('SC','South')
)
INSERT INTO gmv_fact (metric_date, segment_dim, segment_value, gmv, order_count)
SELECT
    o.order_purchase_timestamp::date AS metric_date,
    'region',
    COALESCE(sm.region, 'Unknown')   AS segment_value,
    SUM(oi.price)                    AS gmv,
    COUNT(DISTINCT o.order_id)       AS order_count
FROM raw_order_items oi
JOIN raw_orders o     ON oi.order_id  = o.order_id
JOIN raw_customers c  ON o.customer_id = c.customer_id
LEFT JOIN state_map sm ON c.customer_state = sm.state
WHERE o.order_status IN ('delivered','shipped','invoiced')
  AND o.order_purchase_timestamp::date BETWEEN '2017-01-01' AND '2018-08-31'
GROUP BY 1, 3
ON CONFLICT (metric_date, segment_dim, segment_value)
DO UPDATE SET gmv = EXCLUDED.gmv, order_count = EXCLUDED.order_count;

-- ── Daily total ───────────────────────────────────────────────────────────────
INSERT INTO gmv_total (metric_date, gmv, order_count)
SELECT
    o.order_purchase_timestamp::date AS metric_date,
    SUM(oi.price)                    AS gmv,
    COUNT(DISTINCT o.order_id)       AS order_count
FROM raw_order_items oi
JOIN raw_orders o ON oi.order_id = o.order_id
WHERE o.order_status IN ('delivered','shipped','invoiced')
  AND o.order_purchase_timestamp::date BETWEEN '2017-01-01' AND '2018-08-31'
GROUP BY 1
ON CONFLICT (metric_date)
DO UPDATE SET gmv = EXCLUDED.gmv, order_count = EXCLUDED.order_count;
