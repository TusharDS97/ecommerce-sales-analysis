-- 03_analysis_queries.sql
-- The business questions, one query each. Every query starts with the question in
-- plain words and why anyone would care. Run them in order, or one at a time.
--
-- Money is in rupees. "lakh" = 100,000 (so 6.1 crore shows up as 610.1 lakh).
-- All of these read from the views built in 02_clean_and_model.sql.


-- Q01 Did the cleaning do what I think it did?
-- Before trusting any number I want a receipt: how many rows came in, how many
-- went out, and how many values I had to fill in.
SELECT
    (SELECT COUNT(*) FROM raw_orders)                          AS raw_order_lines,
    (SELECT COUNT(*) FROM orders_clean)                        AS clean_order_lines,
    (SELECT COUNT(*) FROM raw_orders) - (SELECT COUNT(*) FROM orders_clean) AS duplicates_removed,
    (SELECT SUM(delivery_days_imputed) FROM orders_clean)      AS delivery_days_filled,
    (SELECT SUM(age_imputed) FROM customers_clean)             AS ages_filled;


-- Q02 How big is the business?
-- The headline numbers everything else gets compared against.
SELECT
    ROUND(SUM(revenue)     / 1e5, 1)                   AS gross_revenue_lakh,
    ROUND(SUM(net_revenue) / 1e5, 1)                   AS net_revenue_lakh,
    ROUND(SUM(profit)      / 1e5, 1)                   AS profit_lakh,
    ROUND(100.0 * SUM(profit) / SUM(net_revenue), 1)   AS profit_margin_pct,
    COUNT(DISTINCT order_id)                           AS orders,
    COUNT(DISTINCT customer_id)                        AS buying_customers,
    ROUND(SUM(revenue) / COUNT(DISTINCT order_id), 0)  AS avg_order_value,
    ROUND(100.0 * AVG(returned), 1)                    AS item_return_rate_pct
FROM sales_lines;


-- Q03 Month by month, are we growing?
-- Month-on-month change jumps around because of seasonality, so I also show a
-- 3-month moving average, which is the calmer line to watch.
WITH monthly AS (
    SELECT month, SUM(net_revenue) AS net_revenue
    FROM sales_lines
    GROUP BY month
)
SELECT
    month,
    ROUND(net_revenue / 1e5, 1) AS net_revenue_lakh,
    ROUND(100.0 * (net_revenue - LAG(net_revenue) OVER (ORDER BY month))
                / LAG(net_revenue) OVER (ORDER BY month), 1) AS mom_change_pct,
    ROUND(AVG(net_revenue) OVER (ORDER BY month
                                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) / 1e5, 1) AS moving_avg_3m_lakh
FROM monthly
ORDER BY month;


-- Q04 2025 vs 2024, month by month
-- Same calendar month, one year apart, is the fairest comparison there is.
SELECT
    month_num,
    ROUND(SUM(CASE WHEN year = 2024 THEN net_revenue END) / 1e5, 1) AS y2024_lakh,
    ROUND(SUM(CASE WHEN year = 2025 THEN net_revenue END) / 1e5, 1) AS y2025_lakh,
    ROUND(100.0 * (SUM(CASE WHEN year = 2025 THEN net_revenue END)
                 / SUM(CASE WHEN year = 2024 THEN net_revenue END) - 1), 1) AS growth_pct
FROM sales_lines
GROUP BY month_num
ORDER BY month_num;


-- Q05 How much of the year is the festive season?
-- If October and November are a quarter of annual sales, stock and ad budget
-- have to be planned around them.
SELECT
    year,
    ROUND(SUM(net_revenue) / 1e5, 1) AS full_year_lakh,
    ROUND(SUM(CASE WHEN month_num IN (10, 11) THEN net_revenue END) / 1e5, 1) AS oct_nov_lakh,
    ROUND(100.0 * SUM(CASE WHEN month_num IN (10, 11) THEN net_revenue END)
                / SUM(net_revenue), 1) AS oct_nov_share_pct
FROM sales_lines
GROUP BY year;


-- Q06 Which categories sell the most, and which actually make money?
-- Big revenue and good margin are not the same thing, so they sit side by side.
SELECT
    category,
    ROUND(SUM(net_revenue) / 1e5, 1)                     AS net_revenue_lakh,
    ROUND(SUM(profit) / 1e5, 1)                          AS profit_lakh,
    ROUND(100.0 * SUM(profit) / SUM(net_revenue), 1)     AS margin_pct,
    ROUND(100.0 * AVG(returned), 1)                      AS return_rate_pct
FROM sales_lines
GROUP BY category
ORDER BY net_revenue_lakh DESC;


-- Q07 Top 3 products by profit inside each category
-- A window function with PARTITION BY ranks products within their own category,
-- which is the classic "top N per group" interview question.
WITH product_profit AS (
    SELECT category, product_name, SUM(profit) AS profit, SUM(net_revenue) AS net_revenue
    FROM sales_lines
    GROUP BY category, product_name
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY category ORDER BY profit DESC) AS rank_in_category
    FROM product_profit
)
SELECT category, rank_in_category, product_name,
       ROUND(profit / 1e5, 1) AS profit_lakh,
       ROUND(net_revenue / 1e5, 1) AS net_revenue_lakh
FROM ranked
WHERE rank_in_category <= 3
ORDER BY category, rank_in_category;


-- Q08 Which days of the week are busiest?
-- First total each calendar day, then average those days by weekday. Averaging raw
-- rows instead would just tell me which weekday has more rows.
WITH daily AS (
    SELECT order_date, dow, SUM(net_revenue) AS net_revenue
    FROM sales_lines
    GROUP BY order_date, dow
)
SELECT
    CASE dow WHEN 0 THEN 'Sun' WHEN 1 THEN 'Mon' WHEN 2 THEN 'Tue' WHEN 3 THEN 'Wed'
             WHEN 4 THEN 'Thu' WHEN 5 THEN 'Fri' ELSE 'Sat' END AS weekday,
    ROUND(AVG(net_revenue), 0) AS avg_daily_net_revenue
FROM daily
GROUP BY dow
ORDER BY (dow + 6) % 7;   -- puts Monday first


-- Q09 How much more do weekends sell?
-- One number for the slide: weekend average vs weekday average.
WITH daily AS (
    SELECT order_date, dow, SUM(net_revenue) AS net_revenue
    FROM sales_lines
    GROUP BY order_date, dow
),
by_weekday AS (
    SELECT dow, AVG(net_revenue) AS avg_net FROM daily GROUP BY dow
)
SELECT ROUND(100.0 * (AVG(CASE WHEN dow IN (0, 6) THEN avg_net END)
                    / AVG(CASE WHEN dow NOT IN (0, 6) THEN avg_net END) - 1), 1) AS weekend_uplift_pct
FROM by_weekday;


-- Q10 Where do our customers live?
-- SUM() OVER () gives the grand total on every row, so each city's share is one
-- division away. No second query needed.
SELECT
    city,
    ROUND(SUM(net_revenue) / 1e5, 1) AS net_revenue_lakh,
    ROUND(100.0 * SUM(net_revenue) / SUM(SUM(net_revenue)) OVER (), 1) AS share_pct,
    ROUND(100.0 * SUM(SUM(net_revenue)) OVER (ORDER BY SUM(net_revenue) DESC)
                / SUM(SUM(net_revenue)) OVER (), 1) AS running_share_pct
FROM sales_lines
GROUP BY city
ORDER BY net_revenue_lakh DESC;


-- Q11 Why do orders come back? Payment method and category together
-- Each cell is the share of items returned. The corner I expect to hurt is
-- Cash on Delivery with Fashion.
SELECT
    payment_method,
    ROUND(100.0 * AVG(CASE WHEN category = 'Fashion'            THEN returned END), 1) AS fashion_pct,
    ROUND(100.0 * AVG(CASE WHEN category = 'Electronics'        THEN returned END), 1) AS electronics_pct,
    ROUND(100.0 * AVG(CASE WHEN category = 'Home & Kitchen'     THEN returned END), 1) AS home_kitchen_pct,
    ROUND(100.0 * AVG(CASE WHEN category = 'Beauty'             THEN returned END), 1) AS beauty_pct,
    ROUND(100.0 * AVG(CASE WHEN category = 'Books & Stationery' THEN returned END), 1) AS books_pct,
    ROUND(100.0 * AVG(returned), 1)                                                    AS all_items_pct,
    COUNT(*)                                                                           AS items
FROM sales_lines
GROUP BY payment_method
ORDER BY all_items_pct DESC;


-- Q12 Do deeper discounts mean more returns?
-- I show the item count next to each rate, because a rate built on 67 items
-- (the 30%+ band) should not be trusted the way one built on 13,000 can be.
SELECT
    CASE WHEN discount_pct <= 0.05 THEN '0-5%'
         WHEN discount_pct <= 0.10 THEN '5-10%'
         WHEN discount_pct <= 0.20 THEN '10-20%'
         WHEN discount_pct <= 0.30 THEN '20-30%'
         ELSE '30%+' END                       AS discount_band,
    COUNT(*)                                   AS items,
    ROUND(100.0 * AVG(returned), 1)            AS return_rate_pct
FROM sales_lines
GROUP BY discount_band
ORDER BY MIN(discount_pct);


-- Q13 Who are our customers? RFM segments
-- Recency (how recently), Frequency (how often), Monetary (how much). The question
-- is whether a small group carries most of the revenue.
SELECT
    segment,
    COUNT(*)                                                      AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)            AS customer_share_pct,
    ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1)  AS revenue_share_pct,
    ROUND(AVG(frequency), 1)                                      AS avg_orders,
    ROUND(AVG(recency_days), 0)                                   AS avg_days_since_last_order
FROM rfm_scored
GROUP BY segment
ORDER BY revenue_share_pct DESC;


-- Q14 How much do the top 10% of customers matter?
-- ROW_NUMBER over spend, keep the first 10%, add it up.
WITH ranked AS (
    SELECT monetary,
           ROW_NUMBER() OVER (ORDER BY monetary DESC) AS rn,
           COUNT(*) OVER ()                           AS n
    FROM rfm_base
)
SELECT ROUND(100.0 * SUM(CASE WHEN rn <= CAST(n * 0.10 AS INTEGER) THEN monetary END)
                   / SUM(monetary), 1) AS top10pct_customers_revenue_share_pct
FROM ranked;


-- Q15 Do customers come back? Cohort retention
-- Group customers by the month of their first order. Then ask what share of them
-- ordered again 1, 3, 6 and 12 months later. I only count cohorts that are old
-- enough to have been observed that long, otherwise the recent ones would drag
-- the number down for no reason.
WITH first_month AS (
    SELECT customer_id, MIN(month_idx) AS cohort FROM customer_months GROUP BY customer_id
),
cohort_size AS (
    SELECT cohort, COUNT(*) AS n FROM first_month GROUP BY cohort
),
active AS (
    SELECT f.cohort, m.month_idx - f.cohort AS k, COUNT(DISTINCT m.customer_id) AS active_customers
    FROM customer_months m
    JOIN first_month f ON f.customer_id = m.customer_id
    GROUP BY f.cohort, m.month_idx - f.cohort
),
last_month AS (
    SELECT MAX(month_idx) AS last_idx FROM customer_months
),
months_after AS (
    SELECT 1 AS k UNION ALL SELECT 3 UNION ALL SELECT 6 UNION ALL SELECT 12
)
SELECT
    ma.k AS months_after_first_order,
    ROUND(100.0 *
        (SELECT COALESCE(SUM(a.active_customers), 0) FROM active a
          WHERE a.k = ma.k AND (SELECT last_idx FROM last_month) - a.cohort >= ma.k)
      / (SELECT SUM(cs.n) FROM cohort_size cs
          WHERE (SELECT last_idx FROM last_month) - cs.cohort >= ma.k), 1) AS pooled_retention_pct
FROM months_after ma
ORDER BY ma.k;


-- Q16 Which acquisition channel brings the best customers?
-- Sign-ups are cheap to count. What matters is who actually keeps buying.
WITH per_customer AS (
    SELECT customer_id, acquisition_channel,
           COUNT(DISTINCT order_id) AS orders,
           SUM(net_revenue)         AS net_revenue
    FROM sales_lines
    GROUP BY customer_id, acquisition_channel
)
SELECT
    acquisition_channel,
    COUNT(*)                                          AS buying_customers,
    ROUND(AVG(orders), 2)                             AS orders_per_customer,
    ROUND(AVG(net_revenue), 0)                        AS net_revenue_per_customer,
    ROUND(100.0 * AVG(CASE WHEN orders >= 2 THEN 1.0 ELSE 0 END), 1) AS repeat_rate_pct
FROM per_customer
GROUP BY acquisition_channel
ORDER BY net_revenue_per_customer DESC;


-- Q17 Who should we win back first?
-- The 'At risk' group: they used to buy often, and have gone quiet. Sorted by how
-- much they have spent, so the marketing team starts with the most valuable ones.
SELECT
    r.customer_id,
    c.city,
    c.acquisition_channel,
    r.frequency        AS orders_so_far,
    ROUND(r.monetary)  AS net_spend,
    r.recency_days     AS days_since_last_order
FROM rfm_scored r
JOIN customers_clean c ON c.customer_id = r.customer_id
WHERE r.segment = 'At risk'
ORDER BY r.monetary DESC
LIMIT 20;
