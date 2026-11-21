-- 04_powerbi_views.sql
-- Step 4: shape the clean data into the tables Power BI likes best.
--
-- Power BI works best with a "star": one tall table of events in the middle (the
-- fact table, here one row per item sold) and small descriptive tables around it
-- (dimensions: customers, products, dates). Filters flow from the small tables
-- into the big one, which is what makes slicers feel instant.
--
--              dim_date
--                 |
--  dim_customers -+- fact_orders -+- dim_products
--
-- I keep money columns raw (line_revenue, line_cost, returned_flag). Net revenue,
-- profit and the rest are DAX measures in powerbi/measures.dax, so they respond
-- to whatever the viewer filters.

DROP VIEW IF EXISTS pbi_fact_orders;
CREATE VIEW pbi_fact_orders AS
SELECT
    o.order_id || '-' || o.product_id                AS line_id,
    o.order_id,
    o.order_date,
    o.customer_id,
    o.product_id,
    o.quantity,
    o.discount_pct,
    CASE WHEN o.discount_pct <= 0.05 THEN '0-5%'
         WHEN o.discount_pct <= 0.10 THEN '5-10%'
         WHEN o.discount_pct <= 0.20 THEN '10-20%'
         WHEN o.discount_pct <= 0.30 THEN '20-30%'
         ELSE '30%+' END                             AS discount_band,
    CASE WHEN o.discount_pct <= 0.05 THEN 1
         WHEN o.discount_pct <= 0.10 THEN 2
         WHEN o.discount_pct <= 0.20 THEN 3
         WHEN o.discount_pct <= 0.30 THEN 4
         ELSE 5 END                                  AS discount_band_order,
    o.payment_method,
    o.returned                                       AS returned_flag,
    o.unit_price,
    o.shipping_fee,
    o.delivery_days,
    ROUND(o.unit_price * o.quantity, 2)              AS line_revenue,
    ROUND(p.unit_cost  * o.quantity, 2)              AS line_cost
FROM orders_clean o
JOIN products_clean p ON p.product_id = o.product_id;

DROP VIEW IF EXISTS pbi_dim_products;
CREATE VIEW pbi_dim_products AS
SELECT
    product_id,
    product_name,
    category,
    list_price,
    unit_cost,
    ROUND(100.0 * (list_price - unit_cost) / list_price, 1) AS list_margin_pct
FROM products_clean;

-- Customers, with their RFM segment attached. Note the segment is a snapshot as of
-- the last day of data, so it does not change when someone moves a date slicer.
DROP VIEW IF EXISTS pbi_dim_customers;
CREATE VIEW pbi_dim_customers AS
SELECT
    c.customer_id,
    c.city,
    c.gender,
    CAST(c.age AS INTEGER)                       AS age,
    c.signup_date,
    c.acquisition_channel,
    COALESCE(r.segment, 'No purchases')          AS rfm_segment,
    r.recency_days,
    r.frequency                                  AS lifetime_orders,
    ROUND(r.monetary, 2)                         AS lifetime_net_spend,
    r.R                                          AS r_score,
    r.F                                          AS f_score,
    r.M                                          AS m_score,
    (SELECT MIN(order_date) FROM orders_clean oc WHERE oc.customer_id = c.customer_id) AS first_order_date
FROM customers_clean c
LEFT JOIN rfm_scored r ON r.customer_id = c.customer_id;

-- A calendar table. Power BI needs one for "same period last year" style maths.
DROP VIEW IF EXISTS pbi_dim_date;
CREATE VIEW pbi_dim_date AS
WITH RECURSIVE d(dt) AS (
    SELECT date('2024-01-01')
    UNION ALL
    SELECT date(dt, '+1 day') FROM d WHERE dt < date('2025-12-31')
)
SELECT
    dt                                                         AS date,
    CAST(strftime('%Y', dt) AS INTEGER)                        AS year,
    CAST(strftime('%m', dt) AS INTEGER)                        AS month_num,
    CASE strftime('%m', dt)
        WHEN '01' THEN 'Jan' WHEN '02' THEN 'Feb' WHEN '03' THEN 'Mar' WHEN '04' THEN 'Apr'
        WHEN '05' THEN 'May' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul' WHEN '08' THEN 'Aug'
        WHEN '09' THEN 'Sep' WHEN '10' THEN 'Oct' WHEN '11' THEN 'Nov' ELSE 'Dec' END AS month_name,
    strftime('%Y-%m', dt)                                      AS year_month,
    date(dt, 'start of month')                                 AS month_start,
    'Q' || ((CAST(strftime('%m', dt) AS INTEGER) + 2) / 3)     AS quarter,
    (CAST(strftime('%w', dt) AS INTEGER) + 6) % 7 + 1          AS weekday_num,   -- 1 = Monday
    CASE strftime('%w', dt)
        WHEN '1' THEN 'Mon' WHEN '2' THEN 'Tue' WHEN '3' THEN 'Wed' WHEN '4' THEN 'Thu'
        WHEN '5' THEN 'Fri' WHEN '6' THEN 'Sat' ELSE 'Sun' END AS weekday_name,
    CASE WHEN strftime('%w', dt) IN ('0', '6') THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    CASE WHEN strftime('%m', dt) IN ('10', '11') THEN 'Festive (Oct-Nov)' ELSE 'Regular' END AS season
FROM d;

-- Cohort retention, one row per cohort per month-since-first-order.
-- Cells that have not happened yet (e.g. 12 months after a cohort that started
-- last month) are left out, so they show up blank instead of as a misleading 0%.
DROP VIEW IF EXISTS pbi_cohort_retention;
CREATE VIEW pbi_cohort_retention AS
WITH RECURSIVE nums(k) AS (
    SELECT 0 UNION ALL SELECT k + 1 FROM nums WHERE k < 23
),
first_month AS (
    SELECT customer_id, MIN(month_idx) AS cohort FROM customer_months GROUP BY customer_id
),
cohort_size AS (
    SELECT cohort, COUNT(*) AS cohort_size FROM first_month GROUP BY cohort
),
active AS (
    SELECT f.cohort, m.month_idx - f.cohort AS k, COUNT(DISTINCT m.customer_id) AS active_customers
    FROM customer_months m
    JOIN first_month f ON f.customer_id = m.customer_id
    GROUP BY f.cohort, m.month_idx - f.cohort
),
last_month AS (SELECT MAX(month_idx) AS last_idx FROM customer_months)
SELECT
    printf('%04d-%02d-01', cs.cohort / 12, cs.cohort % 12 + 1) AS cohort_month,
    n.k                                                        AS months_since_first_order,
    cs.cohort_size,
    COALESCE(a.active_customers, 0)                            AS active_customers,
    ROUND(100.0 * COALESCE(a.active_customers, 0) / cs.cohort_size, 1) AS retention_pct
FROM cohort_size cs
CROSS JOIN nums n
CROSS JOIN last_month lm
LEFT JOIN active a ON a.cohort = cs.cohort AND a.k = n.k
WHERE n.k <= lm.last_idx - cs.cohort
ORDER BY cs.cohort, n.k;
