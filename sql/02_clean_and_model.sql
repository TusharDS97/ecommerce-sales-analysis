-- 02_clean_and_model.sql
-- Step 2: clean the raw tables, then build a few reusable views so the analysis
-- queries stay short and readable.
--
-- What I fix, and why:
--   * Duplicate lines      -> the same item logged twice would inflate revenue
--   * Payment labels       -> 'upi' and 'UPI' must count as one method
--   * Missing delivery days / ages -> filled with the median, and I keep a flag so
--                            it is always clear which values were filled in
--   * Spaces in city names -> 'Pune ' and 'Pune' are the same city
--   * returned 'True'/'False' text -> 1 / 0 so it can be summed and averaged

-- ---------------------------------------------------------------------------
-- Orders
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS orders_clean;
CREATE TABLE orders_clean AS
WITH numbered AS (
    -- If the same order / product / quantity / customer / date shows up more than
    -- once, rn = 1 is the first copy and rn = 2, 3... are the duplicates.
    SELECT r.*,
           ROW_NUMBER() OVER (
               PARTITION BY order_id, product_id, quantity, customer_id, order_date
               ORDER BY rowid
           ) AS rn
    FROM raw_orders r
),
deduped AS (
    SELECT * FROM numbered WHERE rn = 1
),
median_delivery AS (
    -- SQLite has no MEDIAN(), so: take the middle one or two values and average them.
    SELECT AVG(delivery_days) AS m
    FROM (
        SELECT delivery_days
        FROM deduped
        WHERE delivery_days IS NOT NULL
        ORDER BY delivery_days
        LIMIT  2 - (SELECT COUNT(*) FROM deduped WHERE delivery_days IS NOT NULL) % 2
        OFFSET (SELECT (COUNT(*) - 1) / 2 FROM deduped WHERE delivery_days IS NOT NULL)
    )
)
SELECT
    order_id,
    order_date,
    customer_id,
    product_id,
    quantity,
    discount_pct,
    CASE LOWER(TRIM(payment_method))
        WHEN 'upi'              THEN 'UPI'
        WHEN 'cod'              THEN 'Cash on Delivery'
        WHEN 'cash on delivery' THEN 'Cash on Delivery'
        WHEN 'credit card'      THEN 'Credit Card'
        WHEN 'debit card'       THEN 'Debit Card'
        WHEN 'net banking'      THEN 'Net Banking'
        WHEN 'wallet'           THEN 'Wallet'
        ELSE TRIM(payment_method)
    END                                                   AS payment_method,
    CASE WHEN returned IN ('True', 'TRUE', 'true', '1') THEN 1 ELSE 0 END AS returned,
    unit_price,
    shipping_fee,
    COALESCE(delivery_days, (SELECT m FROM median_delivery)) AS delivery_days,
    CASE WHEN delivery_days IS NULL THEN 1 ELSE 0 END        AS delivery_days_imputed
FROM deduped;

-- ---------------------------------------------------------------------------
-- Customers
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS customers_clean;
CREATE TABLE customers_clean AS
WITH median_age AS (
    SELECT AVG(age) AS m
    FROM (
        SELECT age FROM raw_customers
        WHERE age IS NOT NULL
        ORDER BY age
        LIMIT  2 - (SELECT COUNT(*) FROM raw_customers WHERE age IS NOT NULL) % 2
        OFFSET (SELECT (COUNT(*) - 1) / 2 FROM raw_customers WHERE age IS NOT NULL)
    )
)
SELECT
    customer_id,
    TRIM(city)                                  AS city,
    gender,
    COALESCE(age, (SELECT m FROM median_age))   AS age,
    CASE WHEN age IS NULL THEN 1 ELSE 0 END     AS age_imputed,
    signup_date,
    acquisition_channel
FROM raw_customers;

-- ---------------------------------------------------------------------------
-- Products (already tidy, copied so everything downstream reads *_clean tables)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS products_clean;
CREATE TABLE products_clean AS SELECT * FROM raw_products;

-- ---------------------------------------------------------------------------
-- View: sales_lines  (one row per item sold, with the money worked out)
--
--   revenue     = what the customer paid for the item
--   net_revenue = revenue, but 0 if the item came back (I assume a full refund)
--   profit      = net revenue minus what the product cost us, 0 if returned
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS sales_lines;
CREATE VIEW sales_lines AS
SELECT
    o.order_id,
    o.order_date,
    strftime('%Y-%m', o.order_date)                          AS month,
    CAST(strftime('%Y', o.order_date) AS INTEGER)            AS year,
    CAST(strftime('%m', o.order_date) AS INTEGER)            AS month_num,
    CAST(strftime('%w', o.order_date) AS INTEGER)            AS dow,        -- 0 = Sunday
    o.customer_id,
    o.product_id,
    p.product_name,
    p.category,
    c.city,
    c.acquisition_channel,
    o.quantity,
    o.discount_pct,
    o.payment_method,
    o.returned,
    o.unit_price * o.quantity                                AS revenue,
    CASE WHEN o.returned = 1 THEN 0
         ELSE o.unit_price * o.quantity END                  AS net_revenue,
    CASE WHEN o.returned = 1 THEN 0
         ELSE (o.unit_price - p.unit_cost) * o.quantity END  AS profit,
    p.unit_cost * o.quantity                                 AS line_cost
FROM orders_clean o
JOIN products_clean  p ON p.product_id  = o.product_id
JOIN customers_clean c ON c.customer_id = o.customer_id;

-- ---------------------------------------------------------------------------
-- View: customer_months  (which months did each customer order in?)
-- month_idx is just year*12 + month, so "months between" is simple subtraction.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS customer_months;
CREATE VIEW customer_months AS
SELECT DISTINCT
    customer_id,
    year * 12 + month_num - 1 AS month_idx
FROM sales_lines;

-- ---------------------------------------------------------------------------
-- View: rfm_scored  (Recency, Frequency, Monetary: a score of 1-5 on each)
--
-- Scores come from each customer's rank among all buyers. Customers with identical
-- values share one rank (the average), so two people who behave the same never
-- land in different groups by accident.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS rfm_base;
CREATE VIEW rfm_base AS
SELECT
    customer_id,
    MAX(order_date)                                         AS last_order,
    COUNT(DISTINCT order_id)                                AS frequency,
    SUM(net_revenue)                                        AS monetary,
    -- days from the last order to "the day after the data ends"
    CAST(julianday((SELECT date(MAX(order_date), '+1 day') FROM orders_clean))
         - julianday(MAX(order_date)) AS INTEGER)           AS recency_days
FROM sales_lines
GROUP BY customer_id;

DROP VIEW IF EXISTS rfm_scored;
CREATE VIEW rfm_scored AS
WITH ranked AS (
    SELECT b.*,
           -- big recency (long ago) = low rank = low score
           RANK() OVER (ORDER BY recency_days DESC)
             + (COUNT(*) OVER (PARTITION BY recency_days) - 1) / 2.0 AS r_rank,
           RANK() OVER (ORDER BY frequency)
             + (COUNT(*) OVER (PARTITION BY frequency) - 1) / 2.0     AS f_rank,
           RANK() OVER (ORDER BY monetary)
             + (COUNT(*) OVER (PARTITION BY monetary) - 1) / 2.0      AS m_rank,
           COUNT(*) OVER ()                                           AS n
    FROM rfm_base b
),
scored AS (
    -- ceiling of (rank / n * 5), written without CEIL() so it runs anywhere
    SELECT *,
        CAST(r_rank * 5.0 / n AS INTEGER) + (r_rank * 5.0 / n > CAST(r_rank * 5.0 / n AS INTEGER)) AS R,
        CAST(f_rank * 5.0 / n AS INTEGER) + (f_rank * 5.0 / n > CAST(f_rank * 5.0 / n AS INTEGER)) AS F,
        CAST(m_rank * 5.0 / n AS INTEGER) + (m_rank * 5.0 / n > CAST(m_rank * 5.0 / n AS INTEGER)) AS M
    FROM ranked
)
SELECT
    customer_id, last_order, frequency, monetary, recency_days, R, F, M,
    CASE
        WHEN R >= 4 AND F >= 4 THEN 'Champions'        -- bought recently, buy often
        WHEN R >= 3 AND F >= 3 THEN 'Loyal'            -- solid regulars
        WHEN R <= 2 AND F >= 3 THEN 'At risk'          -- used to buy a lot, gone quiet
        WHEN R >= 4 AND F <= 2 THEN 'New / promising'  -- recent, but only just started
        WHEN R <= 2 AND F <= 2 THEN 'Lost'             -- few orders, long ago
        ELSE 'Needs attention'
    END AS segment
FROM scored;
