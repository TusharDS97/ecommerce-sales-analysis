"""
analysis.py  -  E-commerce sales analysis, end to end.

Run:  python3 analysis.py      (after generate_data.py)

Sections
  1. Load + clean            4. Returns deep-dive
  2. Headline KPIs           5. Customers: RFM + cohort retention
  3. Sales patterns          6. Forecast with an honest back-test

Everything the README quotes is written to outputs/key_findings.json,
so the write-up and the code can never drift apart.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sklearn.linear_model import LinearRegression

OUT, TAB = "outputs", "outputs/tables"
os.makedirs(TAB, exist_ok=True)

# ---- chart look: neutral surface, thin marks, quiet grid ----
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQ = LinearSegmentedColormap.from_list("seq", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
plt.rcParams.update({"figure.facecolor": SURF, "savefig.facecolor": SURF, "font.size": 10,
                     "text.color": INK, "axes.labelcolor": INK2, "font.family": "DejaVu Sans"})

lakh = lambda v: f"₹{v / 1e5:,.1f}L"
F = {}  # key findings, filled as we go


def style(ax, grid="y"):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=9, length=3)
    if grid:
        ax.grid(axis=grid, color=GRID, lw=0.8)
        ax.set_axisbelow(True)


def title(ax, t, sub=None):
    ax.set_title(t, loc="left", fontsize=12, fontweight="bold", color=INK, pad=22 if sub else 10)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=INK2, va="bottom")


def hbar(ax, labels, values, fmt, color=BLUE):
    y = np.arange(len(labels))
    ax.barh(y, values, color=color, height=0.62)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    pad = max(values) * 0.015
    for yi, v in zip(y, values):
        ax.text(v + pad, yi, fmt(v), va="center", fontsize=9, color=INK2)
    ax.set_xlim(0, max(values) * 1.22)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    style(ax, grid=None)
    ax.spines["bottom"].set_visible(False)


# ======================================================================
# 1. LOAD + CLEAN
# ======================================================================
orders = pd.read_csv("data/orders.csv", parse_dates=["order_date"])
customers = pd.read_csv("data/customers.csv", parse_dates=["signup_date"])
products = pd.read_csv("data/products.csv")

log = {"raw_order_lines": len(orders)}

# inconsistent labels ("upi", "COD", "credit card") -> one spelling each
orders["payment_method"] = orders["payment_method"].str.strip().replace(
    {"upi": "UPI", "COD": "Cash on Delivery", "credit card": "Credit Card"})

# exact duplicate lines (same order, product, qty, customer, date)
dup_key = ["order_id", "product_id", "quantity", "customer_id", "order_date"]
before = len(orders)
orders = orders.drop_duplicates(subset=dup_key, keep="first")
log["duplicate_lines_removed"] = before - len(orders)

# missing delivery days -> median (kept as a flag so nothing is hidden)
log["missing_delivery_days"] = int(orders["delivery_days"].isna().sum())
orders["delivery_days_imputed"] = orders["delivery_days"].isna()
orders["delivery_days"] = orders["delivery_days"].fillna(orders["delivery_days"].median())

customers["city"] = customers["city"].str.strip()
log["missing_age"] = int(customers["age"].isna().sum())
customers["age"] = customers["age"].fillna(customers["age"].median())
log["clean_order_lines"] = len(orders)
F["cleaning"] = log

df = orders.merge(products, on="product_id").merge(customers, on="customer_id")
df["revenue"] = df["unit_price"] * df["quantity"]                      # what the customer paid
df["net_revenue"] = np.where(df["returned"], 0, df["revenue"])         # returns fully refunded
df["profit"] = np.where(df["returned"], 0, df["revenue"] - df["unit_cost"] * df["quantity"])
df["month_idx"] = df["order_date"].dt.year * 12 + df["order_date"].dt.month - 1
df["month"] = df["order_date"].dt.to_period("M").dt.to_timestamp()
df["year"] = df["order_date"].dt.year

# ======================================================================
# 2. HEADLINE KPIs
# ======================================================================
gross, net, profit = df["revenue"].sum(), df["net_revenue"].sum(), df["profit"].sum()
n_orders = df["order_id"].nunique()
by_year = df.groupby("year")["net_revenue"].sum()
F["kpi"] = {
    "gross_revenue": gross, "net_revenue": net, "profit": profit,
    "profit_margin_pct": profit / net * 100,
    "orders": n_orders, "customers_who_bought": df["customer_id"].nunique(),
    "aov_gross": gross / n_orders,
    "line_return_rate_pct": df["returned"].mean() * 100,
    "revenue_lost_to_returns_pct": (1 - net / gross) * 100,
    "net_revenue_2024": by_year[2024], "net_revenue_2025": by_year[2025],
    "yoy_growth_pct": (by_year[2025] / by_year[2024] - 1) * 100,
}

# ======================================================================
# 3. SALES PATTERNS
# ======================================================================
monthly = df.groupby("month").agg(net_revenue=("net_revenue", "sum"), gross_revenue=("revenue", "sum"),
                                  profit=("profit", "sum"), orders=("order_id", "nunique"))
monthly.to_csv(f"{TAB}/monthly.csv")

# --- 3a. seasonality (2024 vs 2025 overlaid) ---
pv = monthly["net_revenue"].reset_index()
pv["y"], pv["m"] = pv["month"].dt.year, pv["month"].dt.month
pv = pv.pivot(index="m", columns="y", values="net_revenue")
fig, ax = plt.subplots(figsize=(10, 5))
ax.axvspan(9.5, 11.5, color="#f0efec", zorder=0)
ax.text(10.5, pv.values.max() * 1.0, "Festive\nseason", ha="center", va="top", fontsize=9, color=INK2)
for yr, c in ((2024, BLUE), (2025, ORANGE)):
    ax.plot(pv.index, pv[yr], color=c, lw=2, marker="o", ms=5, mec=SURF, mew=1.5, label=str(yr))
ax.set_xticks(range(1, 13))
ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
ax.yaxis.set_major_formatter(lambda v, _: f"₹{v / 1e5:.0f}L")
ax.set_ylim(0)
style(ax)
ax.legend(frameon=False, loc="upper left", labelcolor=INK)
title(ax, "Revenue peaks in October–November, every year",
      "Net revenue by month (after returns), 2024 vs 2025")
fig.tight_layout()
fig.savefig(f"{OUT}/01_seasonality.png", dpi=160)
plt.close(fig)

peak_m = monthly["net_revenue"].idxmax()
festive = df[df["month"].dt.month.isin([10, 11])].groupby("year")["net_revenue"].sum() / by_year
F["seasonality"] = {"peak_month": str(peak_m.date())[:7], "peak_month_net": monthly["net_revenue"].max(),
                    "festive_share_2024_pct": festive[2024] * 100, "festive_share_2025_pct": festive[2025] * 100,
                    "oct_vs_median_month_x": monthly.loc["2025-10-01", "net_revenue"] / monthly.loc["2025-01-01":"2025-09-01", "net_revenue"].median()}

# --- 3b. category: big sellers vs. money makers ---
cat = df.groupby("category").agg(net_revenue=("net_revenue", "sum"), profit=("profit", "sum"),
                                 return_rate=("returned", "mean"), units=("quantity", "sum"))
cat["margin_pct"] = cat["profit"] / cat["net_revenue"] * 100
cat["return_rate_pct"] = cat["return_rate"] * 100
cat = cat.sort_values("net_revenue", ascending=False)
cat.drop(columns="return_rate").to_csv(f"{TAB}/category.csv")
fig, axs = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"wspace": 0.5})
hbar(axs[0], cat.index, cat["net_revenue"].values, lakh)
title(axs[0], "Net revenue", "Where the sales come from")
ms = cat.sort_values("margin_pct", ascending=False)
hbar(axs[1], ms.index, ms["margin_pct"].values, lambda v: f"{v:.1f}%")
title(axs[1], "Profit margin", "What we keep after product cost and returns")
fig.savefig(f"{OUT}/02_category_revenue_vs_margin.png", dpi=160, bbox_inches="tight")
plt.close(fig)
F["category"] = {c: {"net_revenue": r.net_revenue, "margin_pct": r.margin_pct, "return_rate_pct": r.return_rate_pct,
                     "profit": r.profit} for c, r in cat.iterrows()}

# --- 3c. weekday pattern + cities ---
daily = df.groupby("order_date")["net_revenue"].sum()
dow = daily.groupby(daily.index.dayofweek).mean()
names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
fig, axs = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"wspace": 0.45, "width_ratios": [1, 1.1]})
ax = axs[0]
ax.bar(names, dow.values, color=BLUE, width=0.6)
ax.yaxis.set_major_formatter(lambda v, _: f"₹{v / 1e3:.0f}K")
style(ax)
title(ax, "Weekends sell more", "Average daily net revenue by weekday")
city = df.groupby("city")["net_revenue"].sum().sort_values(ascending=False)
top = city.head(8)
hbar(axs[1], top.index, top.values, lakh)
title(axs[1], "Top 8 cities", "Net revenue, full period")
fig.savefig(f"{OUT}/03_weekday_and_cities.png", dpi=160, bbox_inches="tight")
plt.close(fig)
F["patterns"] = {"weekend_uplift_pct": (dow[[5, 6]].mean() / dow[[0, 1, 2, 3, 4]].mean() - 1) * 100,
                 "best_weekday": names[int(dow.idxmax())],
                 "top5_city_share_pct": city.head(5).sum() / city.sum() * 100,
                 "top_city": city.index[0], "top_city_share_pct": city.iloc[0] / city.sum() * 100}

prod = df.groupby(["product_name", "category"]).agg(net_revenue=("net_revenue", "sum"), profit=("profit", "sum"),
                                                   units=("quantity", "sum")).reset_index()
prod.sort_values("net_revenue", ascending=False).to_csv(f"{TAB}/products.csv", index=False)
F["top_product_by_revenue"] = prod.sort_values("net_revenue", ascending=False).iloc[0][["product_name", "net_revenue"]].to_dict()
F["top_product_by_profit"] = prod.sort_values("profit", ascending=False).iloc[0][["product_name", "profit"]].to_dict()

# ======================================================================
# 4. RETURNS DEEP-DIVE
# ======================================================================
df["discount_band"] = pd.cut(df["discount_pct"], [-0.001, 0.05, 0.10, 0.20, 0.30, 0.5],
                             labels=["0–5%", "5–10%", "10–20%", "20–30%", "30%+"])
r_pay = df.groupby("payment_method")["returned"].mean().sort_values(ascending=False) * 100
r_cat = df.groupby("category")["returned"].mean().sort_values(ascending=False) * 100
r_disc = df.groupby("discount_band", observed=True)["returned"].mean() * 100
fig, axs = plt.subplots(1, 3, figsize=(15, 4.4), gridspec_kw={"wspace": 0.55})
hbar(axs[0], r_pay.index, r_pay.values, lambda v: f"{v:.1f}%")
title(axs[0], "By payment method", "Share of items returned")
hbar(axs[1], r_cat.index, r_cat.values, lambda v: f"{v:.1f}%")
title(axs[1], "By category", "Share of items returned")
n_disc = df.groupby("discount_band", observed=True).size()
hbar(axs[2], [f"{b}  (n={n:,})" for b, n in n_disc.items()], r_disc.values, lambda v: f"{v:.1f}%")
title(axs[2], "By discount depth", "Share of items returned; mild effect, thin data above 30%")
fig.savefig(f"{OUT}/04_returns.png", dpi=160, bbox_inches="tight")
plt.close(fig)

cod_fash = df[(df.payment_method == "Cash on Delivery") & (df.category == "Fashion")]["returned"].mean() * 100
upi_book = df[(df.payment_method == "UPI") & (df.category == "Books & Stationery")]["returned"].mean() * 100
F["returns"] = {"by_payment_pct": r_pay.to_dict(), "by_category_pct": r_cat.to_dict(), "by_discount_pct": r_disc.to_dict(),
                "cod_fashion_pct": cod_fash, "upi_books_pct": upi_book,
                "revenue_returned": df.loc[df.returned, "revenue"].sum()}
# how much would we save if COD+Fashion returned at the Fashion-non-COD rate? (what-if, not a promise)
fn = df[(df.category == "Fashion") & (df.payment_method != "Cash on Delivery")]["returned"].mean()
cf = df[(df.payment_method == "Cash on Delivery") & (df.category == "Fashion")]
F["returns"]["whatif_cod_fashion_revenue_recovered"] = cf["revenue"].sum() * (cf["returned"].mean() - fn)

# ======================================================================
# 5. CUSTOMERS: RFM + COHORTS
# ======================================================================
snap = df["order_date"].max() + pd.Timedelta(days=1)
rfm = df.groupby("customer_id").agg(last_order=("order_date", "max"), frequency=("order_id", "nunique"),
                                    monetary=("net_revenue", "sum"))
rfm["recency_days"] = (snap - rfm["last_order"]).dt.days
score = lambda s: np.ceil(s.rank(pct=True, method="average") * 5).clip(1, 5).astype(int)  # ties share a score
rfm["R"], rfm["F"], rfm["M"] = score(-rfm["recency_days"]), score(rfm["frequency"]), score(rfm["monetary"])
rfm["segment"] = np.select(
    [(rfm.R >= 4) & (rfm.F >= 4), (rfm.R >= 3) & (rfm.F >= 3), (rfm.R <= 2) & (rfm.F >= 3),
     (rfm.R >= 4) & (rfm.F <= 2), (rfm.R <= 2) & (rfm.F <= 2)],
    ["Champions", "Loyal", "At risk", "New / promising", "Lost"], default="Needs attention")
seg = rfm.groupby("segment").agg(customers=("M", "size"), net_revenue=("monetary", "sum"),
                                 avg_orders=("frequency", "mean"), avg_recency_days=("recency_days", "mean"))
seg["customer_share_pct"] = seg["customers"] / seg["customers"].sum() * 100
seg["revenue_share_pct"] = seg["net_revenue"] / seg["net_revenue"].sum() * 100
order = ["Champions", "Loyal", "At risk", "New / promising", "Needs attention", "Lost"]
seg = seg.reindex(order)
seg.to_csv(f"{TAB}/rfm_segments.csv")
rfm.to_csv(f"{TAB}/rfm_customers.csv")

fig, ax = plt.subplots(figsize=(10, 5))
y, h = np.arange(len(seg)), 0.36
ax.barh(y - h / 2 - 1.5 / 72, seg["customer_share_pct"], height=h, color=BLUE, label="Share of customers")
ax.barh(y + h / 2 + 1.5 / 72, seg["revenue_share_pct"], height=h, color=ORANGE, label="Share of revenue")
for yi, a, b in zip(y, seg["customer_share_pct"], seg["revenue_share_pct"]):
    ax.text(a + 0.6, yi - h / 2 - 1.5 / 72, f"{a:.0f}%", va="center", fontsize=9, color=INK2)
    ax.text(b + 0.6, yi + h / 2 + 1.5 / 72, f"{b:.0f}%", va="center", fontsize=9, color=INK2)
ax.set_yticks(y)
ax.set_yticklabels(seg.index)
ax.invert_yaxis()
ax.set_xticks([])
style(ax, grid=None)
ax.spines["bottom"].set_visible(False)
ax.legend(frameon=False, loc="lower right", labelcolor=INK)
title(ax, "A small group of customers drives most of the revenue",
      "RFM segments: share of customers vs share of net revenue")
fig.tight_layout()
fig.savefig(f"{OUT}/05_rfm_segments.png", dpi=160)
plt.close(fig)

cust_sorted = rfm["monetary"].sort_values(ascending=False)
top10 = cust_sorted.head(int(len(cust_sorted) * 0.10)).sum() / cust_sorted.sum() * 100
F["customers"] = {"repeat_rate_pct": (rfm["frequency"] >= 2).mean() * 100, "avg_orders_per_customer": rfm["frequency"].mean(),
                  "top10pct_customers_revenue_share_pct": top10,
                  "segments": {k: {"customers": int(r.customers), "customer_share_pct": r.customer_share_pct,
                                   "revenue_share_pct": r.revenue_share_pct} for k, r in seg.iterrows()}}

# --- cohort retention: of the customers whose first order was in month X, how many order again k months later? ---
first = df.groupby("customer_id")["month_idx"].min()
act = df[["customer_id", "month_idx"]].drop_duplicates()
act["cohort"] = act["customer_id"].map(first)
act["k"] = act["month_idx"] - act["cohort"]
co = act.groupby(["cohort", "k"])["customer_id"].nunique().unstack(fill_value=0)
last_idx = df["month_idx"].max()
size = co[0]
ret = co.div(size, axis=0) * 100
for c in ret.index:                                       # months we haven't seen yet are blank, not zero
    ret.loc[c, ret.columns > (last_idx - c)] = np.nan
show = ret.loc[ret.index <= last_idx - 6, list(range(1, 13))]
labels = [f"{c // 12}-{c % 12 + 1:02d}  (n={int(size[c])})" for c in show.index]
fig, ax = plt.subplots(figsize=(11, 7.5))
im = ax.imshow(show.values, cmap=SEQ, aspect="auto", vmin=0, vmax=np.nanmax(show.values))
ax.set_xticks(range(12))
ax.set_xticklabels(range(1, 13))
ax.set_yticks(range(len(labels)))
ax.set_yticklabels(labels, fontsize=8)
ax.set_xlabel("Months since first order")
for i in range(show.shape[0]):
    for j in range(show.shape[1]):
        v = show.values[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                    color="#ffffff" if v > np.nanmax(show.values) * 0.55 else INK)
for s in ax.spines.values():
    s.set_visible(False)
ax.tick_params(colors=INK2, length=0)
title(ax, "Cohort retention: % of each month's new customers who order again",
      "Cohorts with at least 6 months of follow-up; blank = not observable yet")
fig.tight_layout()
fig.savefig(f"{OUT}/06_cohort_retention.png", dpi=160)
plt.close(fig)
ret.to_csv(f"{TAB}/cohort_retention_pct.csv")


def weighted_ret(k):                                      # pooled across cohorts that have reached month k
    ok = [c for c in ret.index if (last_idx - c) >= k]
    return co.loc[ok, k].sum() / size.loc[ok].sum() * 100


F["cohort"] = {f"month_{k}_pooled_retention_pct": weighted_ret(k) for k in (1, 3, 6, 12)}

# ======================================================================
# 6. FORECAST (with a back-test, because a forecast nobody tested is a guess)
# ======================================================================
y = monthly["net_revenue"]


def feats(idx, t0):
    d = pd.DataFrame({"t": np.arange(t0, t0 + len(idx))}, index=idx)
    for k in range(2, 13):
        d[f"m{k}"] = (idx.month == k).astype(int)
    return d


H = 3                                                      # hold out Oct-Dec 2025: the hardest months to call
train, test = y.iloc[:-H], y.iloc[-H:]
mdl = LinearRegression().fit(feats(train.index, 0), np.log(train))
pred_test = pd.Series(np.exp(mdl.predict(feats(test.index, len(train)))), index=test.index)
naive = pd.Series(y.shift(12).iloc[-H:].values, index=test.index)  # "same month last year"
mape = lambda a, p: float(np.mean(np.abs(a - p) / a) * 100)
F["forecast"] = {"backtest_months": [str(i.date())[:7] for i in test.index],
                 "model_mape_pct": mape(test, pred_test), "seasonal_naive_mape_pct": mape(test, naive)}

full = LinearRegression().fit(feats(y.index, 0), np.log(y))
resid = np.log(y) - full.predict(feats(y.index, 0))
# 13 model parameters = intercept + trend + 11 month dummies
sigma = max(float(np.sqrt((resid ** 2).sum() / (len(y) - 13))),
            float(np.sqrt(np.mean((np.log(test) - np.log(pred_test)) ** 2))))
fut_idx = pd.date_range(y.index[-1] + pd.offsets.MonthBegin(1), periods=3, freq="MS")
fc = np.exp(full.predict(feats(fut_idx, len(y))))
fc = pd.DataFrame({"forecast": fc, "low_80": fc * np.exp(-1.28 * sigma), "high_80": fc * np.exp(1.28 * sigma)}, index=fut_idx)
fc.to_csv(f"{TAB}/forecast_next_3_months.csv")
F["forecast"]["next_3_months"] = {str(i.date())[:7]: {"forecast": r.forecast, "low_80": r.low_80, "high_80": r.high_80}
                                  for i, r in fc.iterrows()}

fig, ax = plt.subplots(figsize=(11, 5))
ax.plot(y.index, y.values, color=BLUE, lw=2, label="Actual")
ax.plot(pred_test.index, pred_test.values, color=ORANGE, lw=2, ls="--", marker="o", ms=5, mec=SURF, mew=1.5,
        label="Back-test (model never saw these months)")
ax.fill_between(fc.index, fc["low_80"], fc["high_80"], color=ORANGE, alpha=0.18, lw=0)
ax.plot(fc.index, fc["forecast"], color=ORANGE, lw=2, ls=":", marker="o", ms=5, mec=SURF, mew=1.5,
        label="Forecast, next 3 months (shaded: 80% range)")
ax.yaxis.set_major_formatter(lambda v, _: f"₹{v / 1e5:.0f}L")
ax.set_ylim(0)
style(ax)
ax.legend(frameon=False, loc="upper left", labelcolor=INK)
title(ax, "Forecast: trend + seasonality, tested on held-out months",
      f"Back-test error {F['forecast']['model_mape_pct']:.1f}% vs {F['forecast']['seasonal_naive_mape_pct']:.1f}% for 'same month last year'")
fig.tight_layout()
fig.savefig(f"{OUT}/07_forecast.png", dpi=160)
plt.close(fig)

# ======================================================================
# SAVE + PRINT
# ======================================================================
clean = lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else str(o)
with open(f"{OUT}/key_findings.json", "w") as fh:
    json.dump(F, fh, indent=2, default=clean)
df.drop(columns=["discount_band"]).to_csv(f"{TAB}/orders_clean_joined.csv", index=False)
print(json.dumps(F, indent=2, default=clean))
