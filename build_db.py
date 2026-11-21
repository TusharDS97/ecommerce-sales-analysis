"""
build_db.py - build the SQL database and run every query in sql/03_analysis_queries.sql

    python3 build_db.py

What it does
  1. loads data/*.csv into a SQLite file (ecommerce.db)
  2. runs sql/01 (tables) and sql/02 (cleaning + views)
  3. runs each query in sql/03 and saves its result to sql/results/Qxx.csv
  4. (if sql/04_powerbi_views.sql exists) exports the Power BI tables to powerbi/data/

SQLite ships with Python, so there is nothing to install or set up.
"""
import os
import re
import sqlite3

import pandas as pd

DB = "ecommerce.db"
if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)


def run_script(path):
    with open(path, encoding="utf-8") as fh:
        con.executescript(fh.read())


run_script("sql/01_create_tables.sql")
# returned is read as text so the raw table keeps 'True'/'False' exactly as it arrived
pd.read_csv("data/orders.csv", dtype={"returned": str}).to_sql("raw_orders", con, if_exists="append", index=False)
pd.read_csv("data/customers.csv").to_sql("raw_customers", con, if_exists="append", index=False)
pd.read_csv("data/products.csv").to_sql("raw_products", con, if_exists="append", index=False)
run_script("sql/02_clean_and_model.sql")
print("tables and views built")

# ---- run every query in 03 and save the results ----
os.makedirs("sql/results", exist_ok=True)
name, buf, n_ok = None, "", 0
with open("sql/03_analysis_queries.sql", encoding="utf-8") as fh:
    for line in fh:
        m = re.match(r"--\s*(Q\d+)\b", line)
        if m:
            name = m.group(1)
        buf += line
        if sqlite3.complete_statement(buf):
            if name:
                df = pd.read_sql_query(buf, con)
                df.to_csv(f"sql/results/{name}.csv", index=False)
                n_ok += 1
                print(f"  {name}: {len(df)} rows")
            buf, name = "", None
print(f"{n_ok} queries ran OK -> sql/results/")

# ---- Power BI export (only once 04 exists) ----
if os.path.exists("sql/04_powerbi_views.sql"):
    run_script("sql/04_powerbi_views.sql")
    os.makedirs("powerbi/data", exist_ok=True)
    for view, fname in [("pbi_fact_orders", "fact_orders"), ("pbi_dim_customers", "dim_customers"),
                        ("pbi_dim_products", "dim_products"), ("pbi_dim_date", "dim_date"),
                        ("pbi_cohort_retention", "cohort_retention")]:
        d = pd.read_sql_query(f"SELECT * FROM {view}", con)
        d.to_csv(f"powerbi/data/{fname}.csv", index=False)
        print(f"  powerbi/data/{fname}.csv: {len(d):,} rows")
con.close()
