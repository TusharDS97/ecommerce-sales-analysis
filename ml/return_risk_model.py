"""
return_risk_model.py - Which orders are likely to be returned?

Run from the project folder:
    python ml/return_risk_model.py

The question
    Returns cost us about 10% of revenue. The analysis showed Cash on Delivery and
    Fashion are the hot spots. Can a model score each order by how likely it is to
    come back, so the business could act on the risky ones *before* they ship?

How I built it (the short version)
    1. One row per item sold. The thing to predict is "was it returned?" (yes / no).
    2. Features = only things we know AT THE MOMENT OF ORDER. No peeking.
    3. Train on the older orders, test on the newest six months. That mimics real
       life: a model is always used on orders it has never seen.
    4. Compare three models: a simple rule, logistic regression (my main model,
       because it's easy to explain) and a random forest (to check whether a
       fancier model is worth the trouble).

Outputs go to ml/outputs/.
"""
import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ap = argparse.ArgumentParser()
ap.add_argument("--root", default=".", help="project folder (the one that contains data/)")
ROOT = ap.parse_args().root
OUT = os.path.join(ROOT, "ml", "outputs")
os.makedirs(OUT, exist_ok=True)
SEED = 42

# chart look, same as the rest of the project
SURF, INK, INK2, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#898781"
plt.rcParams.update({"figure.facecolor": SURF, "savefig.facecolor": SURF, "font.size": 10,
                     "text.color": INK, "axes.labelcolor": INK2, "font.family": "DejaVu Sans"})


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


# ======================================================================
# 1. LOAD + CLEAN  (same fixes as the main analysis)
# ======================================================================
orders = pd.read_csv(os.path.join(ROOT, "data", "orders.csv"), parse_dates=["order_date"])
customers = pd.read_csv(os.path.join(ROOT, "data", "customers.csv"))
products = pd.read_csv(os.path.join(ROOT, "data", "products.csv"))

orders["payment_method"] = orders["payment_method"].str.strip().replace(
    {"upi": "UPI", "COD": "Cash on Delivery", "credit card": "Credit Card"})
orders = orders.drop_duplicates(subset=["order_id", "product_id", "quantity", "customer_id", "order_date"])
customers["city"] = customers["city"].str.strip()
customers["age"] = customers["age"].fillna(customers["age"].median())

df = orders.merge(products[["product_id", "category"]], on="product_id") \
           .merge(customers[["customer_id", "city", "age", "acquisition_channel"]], on="customer_id")
df["returned"] = df["returned"].astype(str).str.lower().eq("true").astype(int)

# ======================================================================
# 2. FEATURES - only what is known when the order is placed
#    (I leave out delivery_days on purpose: we only learn it after the order ships,
#     so using it would be "peeking at the future")
# ======================================================================
df["discount_10pts"] = df["discount_pct"] * 10          # +1 = ten more percentage points of discount
df["price_1000s"] = df["unit_price"] / 1000             # +1 = Rs.1,000 more per unit
df["is_festive"] = df["order_date"].dt.month.isin([10, 11]).astype(int)
df["is_weekend"] = (df["order_date"].dt.dayofweek >= 5).astype(int)

CATEGORICAL = ["payment_method", "category", "city", "acquisition_channel"]
NUMERIC = ["discount_10pts", "price_1000s", "quantity", "age", "is_festive", "is_weekend"]
# The reference group each category is compared against (the calm, low-return ones),
# so the results read as "compared with a UPI order of a Books item..."
BASELINE = {"payment_method": "UPI", "category": "Books & Stationery",
            "city": "Mumbai", "acquisition_channel": "Organic Search"}

# ======================================================================
# 3. TRAIN / TEST SPLIT BY TIME
# ======================================================================
CUTOFF = pd.Timestamp("2025-07-01")
train, test = df[df["order_date"] < CUTOFF], df[df["order_date"] >= CUTOFF]
X_tr, y_tr = train[CATEGORICAL + NUMERIC], train["returned"]
X_te, y_te = test[CATEGORICAL + NUMERIC], test["returned"]
print(f"train: {len(train):,} items ({train.order_date.min().date()} to {train.order_date.max().date()}), "
      f"return rate {y_tr.mean() * 100:.1f}%")
print(f"test : {len(test):,} items ({test.order_date.min().date()} to {test.order_date.max().date()}), "
      f"return rate {y_te.mean() * 100:.1f}%")

# ======================================================================
# 4. MODELS
# ======================================================================
def encoder():
    drop = [BASELINE[c] for c in CATEGORICAL]
    return ColumnTransformer([("cat", OneHotEncoder(drop=drop, handle_unknown="ignore"), CATEGORICAL)],
                             remainder="passthrough")


logit = Pipeline([("prep", encoder()), ("model", LogisticRegression(max_iter=1000))]).fit(X_tr, y_tr)
forest = Pipeline([("prep", encoder()),
                   ("model", RandomForestClassifier(n_estimators=300, min_samples_leaf=50,
                                                    random_state=SEED, n_jobs=-1))]).fit(X_tr, y_tr)

# a rule anyone could write on a whiteboard: +1 for Cash on Delivery, +1 for Fashion
rule_score = lambda d: (d["payment_method"] == "Cash on Delivery").astype(int) + (d["category"] == "Fashion").astype(int)

scores = {
    "Always guess the average": np.full(len(test), y_tr.mean()),
    "Simple rule (COD + Fashion)": rule_score(test).values + np.random.default_rng(SEED).uniform(0, 1e-6, len(test)),
    "Logistic regression": logit.predict_proba(X_te)[:, 1],
    "Random forest": forest.predict_proba(X_te)[:, 1],
}

# ======================================================================
# 5. HOW GOOD ARE THEY?
#    AUC: if I pick one returned and one kept order at random, how often does the
#    model give the returned one the higher risk? 0.5 = coin flip, 1.0 = perfect.
# ======================================================================
def top_share(y, s, frac):
    """Share of all returns caught if we look at only the riskiest `frac` of orders."""
    k = int(len(y) * frac)
    idx = np.argsort(-np.asarray(s), kind="stable")[:k]
    return float(np.asarray(y)[idx].sum() / np.sum(y))


metrics = {"train_items": len(train), "test_items": len(test), "cutoff": str(CUTOFF.date()),
           "train_return_rate_pct": y_tr.mean() * 100, "test_return_rate_pct": y_te.mean() * 100, "models": {}}
for name, s in scores.items():
    metrics["models"][name] = {
        "roc_auc": float(roc_auc_score(y_te, s)),
        "avg_precision": float(average_precision_score(y_te, s)),
        "share_of_returns_in_riskiest_10pct": top_share(y_te, s, 0.10),
        "share_of_returns_in_riskiest_20pct": top_share(y_te, s, 0.20),
    }
    m = metrics["models"][name]
    print(f"{name:30s} AUC {m['roc_auc']:.3f} | riskiest 20% of orders hold {m['share_of_returns_in_riskiest_20pct'] * 100:.0f}% of returns")

# ======================================================================
# 6. DOES A PREDICTED 20% MEAN ABOUT 20% IN REAL LIFE?  (risk deciles, logistic model)
# ======================================================================
t = test[["order_id", "product_id", "payment_method", "category", "returned"]].copy()
t["risk_score"] = scores["Logistic regression"]
t["risk_decile"] = pd.qcut(t["risk_score"].rank(method="first"), 10, labels=range(1, 11)).astype(int)
dec = t.groupby("risk_decile").agg(items=("returned", "size"), avg_predicted_pct=("risk_score", "mean"),
                                   actual_return_rate_pct=("returned", "mean"))
dec[["avg_predicted_pct", "actual_return_rate_pct"]] *= 100
dec = dec.round(1)
dec.to_csv(os.path.join(OUT, "risk_deciles.csv"))
metrics["riskiest_decile_actual_return_rate_pct"] = float(dec.loc[10, "actual_return_rate_pct"])
metrics["safest_decile_actual_return_rate_pct"] = float(dec.loc[1, "actual_return_rate_pct"])
t.sort_values("risk_score", ascending=False).round({"risk_score": 4}).to_csv(
    os.path.join(OUT, "order_risk_scores_test.csv"), index=False)

# ======================================================================
# 7. WHAT DID THE MODEL LEARN?  Odds ratios from the logistic regression.
#    "2.0" means the odds of a return are twice as high as the comparison group,
#    holding everything else equal. "1.0" means no effect.
# ======================================================================
names = logit.named_steps["prep"].get_feature_names_out()
coefs = logit.named_steps["model"].coef_[0]
drivers = pd.DataFrame({"feature": names, "odds_ratio": np.exp(coefs)})


def pretty(f):
    for col in CATEGORICAL:                       # e.g. 'cat__payment_method_Credit Card'
        prefix = f"cat__{col}_"
        if f.startswith(prefix):
            return f"{col.replace('_', ' ').capitalize()}: {f[len(prefix):]}  (vs {BASELINE[col]})"
    return {"remainder__discount_10pts": "Discount, per +10 points", "remainder__price_1000s": "Price, per +Rs.1,000",
            "remainder__quantity": "Quantity, per extra unit", "remainder__age": "Age, per year",
            "remainder__is_festive": "Ordered in Oct-Nov", "remainder__is_weekend": "Ordered on a weekend"}[f]


drivers["label"] = drivers["feature"].map(pretty)
drivers = drivers.sort_values("odds_ratio", ascending=False)
drivers[["label", "odds_ratio"]].round(3).to_csv(os.path.join(OUT, "what_drives_returns.csv"), index=False)
metrics["odds_ratios"] = {r.label: float(round(r.odds_ratio, 3)) for r in drivers.itertuples()}

# ======================================================================
# CHARTS
# ======================================================================
# 1. ROC curves
fig, ax = plt.subplots(figsize=(6.5, 5.6))
ax.plot([0, 1], [0, 1], color=GREY, lw=1, ls=":", label="Coin flip (AUC 0.50)")
for name, color, ls in (("Simple rule (COD + Fashion)", GREY, "-"), ("Logistic regression", BLUE, "-"),
                        ("Random forest", ORANGE, "--")):
    fpr, tpr, _ = roc_curve(y_te, scores[name])
    ax.plot(fpr, tpr, color=color, lw=2, ls=ls, label=f"{name} (AUC {metrics['models'][name]['roc_auc']:.2f})")
ax.set_xlabel("Share of kept orders wrongly flagged")
ax.set_ylabel("Share of returned orders caught")
style(ax, grid="both")
ax.legend(frameon=False, loc="lower right", labelcolor=INK, fontsize=9)
title(ax, "A two-line rule is almost as good as any model here",
      "Tested on the newest six months, which the models never saw")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "ml_01_roc.png"), dpi=160)
plt.close(fig)

# 2. what drives returns (odds ratios)
# Only the big effects go on the chart (1.5x or more, either direction). Small differences,
# like one city at 1.3x, come from small groups of orders and are mostly noise, so I
# don't want the chart to invite over-reading. The full list is in what_drives_returns.csv.
keep = drivers[(drivers["odds_ratio"] >= 1.5) | (drivers["odds_ratio"] <= 1 / 1.5)]
fig, ax = plt.subplots(figsize=(9, 0.5 * len(keep) + 1.8))
y = np.arange(len(keep))
ax.barh(y, keep["odds_ratio"] - 1, left=1, color=[ORANGE if v > 1 else BLUE for v in keep["odds_ratio"]], height=0.6)
ax.axvline(1, color=INK2, lw=1)
ax.set_yticks(y)
ax.set_yticklabels(keep["label"], fontsize=9)
ax.invert_yaxis()
for yi, v in zip(y, keep["odds_ratio"]):
    ax.text(v + (0.04 if v > 1 else -0.04), yi, f"{v:.2f}x", va="center", ha="left" if v > 1 else "right", fontsize=9, color=INK2)
ax.set_xlabel("Effect on the odds of a return (1.0 = no effect)")
style(ax, grid="x")
title(ax, "Cash on Delivery and Fashion push returns up the most",
      "Logistic regression. Showing effects of 1.5x or more; everything smaller (cities, channels, other payments) is within noise")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "ml_02_what_drives_returns.png"), dpi=160, bbox_inches="tight")
plt.close(fig)

# 3. risk deciles: predicted vs actual
fig, ax = plt.subplots(figsize=(9, 4.8))
x = np.arange(1, 11)
ax.bar(x, dec["actual_return_rate_pct"], color=BLUE, width=0.62, label="Actual return rate")
ax.plot(x, dec["avg_predicted_pct"], color=ORANGE, lw=2, marker="o", ms=5, mec=SURF, mew=1.5, label="What the model predicted")
ax.axhline(y_te.mean() * 100, color=GREY, lw=1, ls=":")
ax.text(0.55, y_te.mean() * 100 + 0.5, f"Average {y_te.mean() * 100:.1f}%", ha="left", fontsize=9, color=INK2)
for xi, v in zip(x, dec["actual_return_rate_pct"]):          # labels sit inside the bars, clear of the line
    ax.text(xi, 0.8, f"{v:.0f}%", ha="center", fontsize=9, color="#ffffff", fontweight="bold")
ax.set_xticks(x)
ax.set_xlabel("Orders sorted from least risky (1) to most risky (10), 10% in each group")
ax.set_yticks(range(0, 26, 5))
ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
ax.set_ylim(0, 24)
style(ax)
ax.legend(frameon=False, loc="upper left", labelcolor=INK)
title(ax, "The riskiest orders really do come back more often",
      "Return rate by risk group in the six test months, with what the model predicted")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "ml_03_risk_deciles.png"), dpi=160)
plt.close(fig)

with open(os.path.join(OUT, "ml_metrics.json"), "w") as fh:
    json.dump(metrics, fh, indent=2)
print("saved charts + ml_metrics.json to", OUT)
