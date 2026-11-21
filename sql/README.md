# The SQL side

I re-did the core of the analysis in SQL for two reasons. Analysts spend a lot of their week in SQL, and it's the best cross-check I know: if two different tools give the same answer, I trust the answer more.

## Run it (nothing to install)

```bash
python3 build_db.py
```

That loads the CSVs into a SQLite file (`ecommerce.db`), runs the scripts below in order, and saves each query's result to `sql/results/Q01.csv`, `Q02.csv`, and so on. SQLite comes with Python, so there is no server to set up.

If you'd rather click around, open `ecommerce.db` in [DB Browser for SQLite](https://sqlitebrowser.org/) (free) and paste any query from `03_analysis_queries.sql`.

## What's in the folder

| File | What it does |
|---|---|
| `01_create_tables.sql` | Empty tables where the raw CSVs land, messy values and all |
| `02_clean_and_model.sql` | Removes duplicates, fixes labels, fills blanks (with flags), then builds views: `sales_lines`, `rfm_scored`, `customer_months` |
| `03_analysis_queries.sql` | 17 business questions, each with a plain-English "why do I care" comment |
| `04_powerbi_views.sql` | Reshapes the clean data into the tables Power BI uses (fact + dimensions) |

## The 17 questions

| # | Question | SQL idea it shows |
|---|---|---|
| Q01 | Did my cleaning do what I think? | Subqueries as a data "receipt" |
| Q02 | How big is the business? | Aggregates, `COUNT(DISTINCT ...)` |
| Q03 | Are we growing month to month? | `LAG`, moving average with a window frame |
| Q04 | 2025 vs 2024, month by month | Conditional aggregation (`CASE` inside `SUM`) |
| Q05 | How much of the year is the festive season? | Share of total |
| Q06 | Which categories sell most, and which make money? | `GROUP BY`, margin maths |
| Q07 | Top 3 products by profit in each category | `ROW_NUMBER() OVER (PARTITION BY ...)` |
| Q08 | Busiest days of the week | Aggregate twice (days first, then weekdays) |
| Q09 | Weekend uplift | One-number summary from a CTE |
| Q10 | Where do customers live? | Share of total and running total with window functions |
| Q11 | Returns by payment method and category | Pivot-style crosstab |
| Q12 | Do deeper discounts mean more returns? | `CASE` bands, sample size next to a rate |
| Q13 | RFM customer segments | `RANK`, ties handled, `CASE` segmentation |
| Q14 | How much do the top 10% of customers matter? | `ROW_NUMBER` + `COUNT(*) OVER ()` |
| Q15 | Do customers come back? Cohort retention | Self-join, month arithmetic |
| Q16 | Which acquisition channel is best? | CTE then aggregate |
| Q17 | Who should marketing win back first? | Filter a segment, rank by value |

## I checked it against Python

Every headline number from the Python analysis (revenue, profit, margin, returns, city shares, cohort retention) matches the SQL output. That includes the RFM segments, which landed on exactly the same customer counts. That one took care: customers with identical behaviour must share a rank, or ties get split into different segments by accident.

## One thing the data can't tell you

Q16 (acquisition channels) shows almost no difference between channels, about ₹4,750 to ₹5,000 per customer for all five. That isn't a finding. I assigned channels at random when I generated the data, so there is nothing to find. On a real store this is the query that would decide where the ad budget goes.

## Using a different database?

These are written for SQLite and I've only run them there. The logic carries over, but a few functions have different names:

| What | SQLite (used here) | PostgreSQL | MySQL | SQL Server |
|---|---|---|---|---|
| Year-month text | `strftime('%Y-%m', d)` | `TO_CHAR(d, 'YYYY-MM')` | `DATE_FORMAT(d, '%Y-%m')` | `FORMAT(d, 'yyyy-MM')` |
| Day of week | `strftime('%w', d)` (0 = Sun) | `EXTRACT(DOW FROM d)` (0 = Sun) | `DAYOFWEEK(d)` (1 = Sun) | `DATEPART(weekday, d)` |
| Days between | `julianday(a) - julianday(b)` | `a - b` | `DATEDIFF(a, b)` | `DATEDIFF(day, b, a)` |
| Median | middle-row trick (see script 02) | `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY x)` | window trick or `PERCENTILE_CONT` (8.0+) | `PERCENTILE_CONT(0.5) WITHIN GROUP (...) OVER ()` |
| Whole-number cast | `CAST(x AS INTEGER)` | `CAST(x AS INTEGER)` | `CAST(x AS SIGNED)` | `CAST(x AS INT)` |
| Make a table from a query | `CREATE TABLE t AS SELECT ...` | same | same | `SELECT ... INTO t FROM ...` |
| Date calendar | recursive CTE | `generate_series` | recursive CTE | recursive CTE |

Window functions (`ROW_NUMBER`, `RANK`, `LAG`, `SUM() OVER`) work the same in all four.
