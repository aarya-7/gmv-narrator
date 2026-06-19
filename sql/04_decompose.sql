-- Parameterised decomposition query.
-- Bound params: %(anomaly_date)s, %(window_start)s, %(window_end)s, %(segment_dim)s
-- Table suffix: %(table_suffix)s  →  'shocked' or '' (empty = clean tables)

WITH baseline AS (
    SELECT
        segment_value,
        AVG(gmv) AS baseline_gmv
    FROM gmv_fact%(table_suffix)s
    WHERE segment_dim  = %(segment_dim)s
      AND metric_date BETWEEN %(window_start)s AND %(window_end)s
      AND metric_date != %(anomaly_date)s
    GROUP BY segment_value
),
actual AS (
    SELECT segment_value, gmv AS actual_gmv
    FROM gmv_fact%(table_suffix)s
    WHERE segment_dim  = %(segment_dim)s
      AND metric_date = %(anomaly_date)s
),
delta AS (
    SELECT
        a.segment_value,
        a.actual_gmv,
        b.baseline_gmv,
        a.actual_gmv - b.baseline_gmv AS gmv_delta,
        CASE WHEN b.baseline_gmv = 0 THEN NULL
             ELSE (a.actual_gmv - b.baseline_gmv) / b.baseline_gmv * 100
        END AS pct_change
    FROM actual a
    JOIN baseline b USING (segment_value)
),
totals AS (
    SELECT SUM(gmv_delta) AS total_delta FROM delta
)
SELECT
    d.segment_value,
    d.actual_gmv,
    d.baseline_gmv,
    d.gmv_delta,
    d.pct_change,
    CASE WHEN t.total_delta = 0 THEN NULL
         ELSE d.gmv_delta / t.total_delta * 100
    END AS contribution_pct,
    CASE WHEN d.gmv_delta < 0 THEN 'down' ELSE 'up' END AS direction,
    t.total_delta
FROM delta d
CROSS JOIN totals t
ORDER BY ABS(d.gmv_delta) DESC
LIMIT 5;
