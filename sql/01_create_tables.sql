-- 01_create_tables.sql
-- Step 1: somewhere for the raw CSVs to land.
--
-- I keep the raw tables exactly as the files arrive (messy labels, duplicates, blanks
-- and all). Cleaning happens in the next script, so I can always point back at what
-- the original data looked like.
--
-- Written for SQLite so anyone can run it with no server. Dialect notes for
-- MySQL / PostgreSQL / SQL Server are in sql/README.md.

DROP TABLE IF EXISTS raw_orders;
CREATE TABLE raw_orders (
    order_id        TEXT,
    order_date      TEXT,      -- 'YYYY-MM-DD'
    customer_id     TEXT,
    product_id      TEXT,
    quantity        INTEGER,
    discount_pct    REAL,
    payment_method  TEXT,      -- messy: 'upi', 'UPI', 'COD', 'Cash on Delivery' ...
    returned        TEXT,      -- arrives as the text 'True' / 'False'
    unit_price      REAL,      -- price after discount
    shipping_fee    REAL,
    delivery_days   REAL       -- some blanks
);

DROP TABLE IF EXISTS raw_customers;
CREATE TABLE raw_customers (
    customer_id          TEXT,
    city                 TEXT,   -- a few have trailing spaces
    gender               TEXT,
    age                  REAL,   -- some blanks
    signup_date          TEXT,
    acquisition_channel  TEXT
);

DROP TABLE IF EXISTS raw_products;
CREATE TABLE raw_products (
    product_id    TEXT,
    product_name  TEXT,
    category      TEXT,
    list_price    REAL,
    unit_cost     REAL
);
