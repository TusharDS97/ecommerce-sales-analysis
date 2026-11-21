"""
generate_data.py
Builds a synthetic-but-realistic Indian e-commerce dataset (Jan 2024 - Dec 2025).

Why synthetic? Real company data is private. This one is built with the patterns
you'd actually see: Diwali spikes, weekend bumps, COD returns being higher,
a mix of one-time and repeat buyers, a few messy values to clean.
Seeded, so everyone who runs it gets the same numbers.

Honest note for interviews: because I built the patterns in, the analysis can
"find" them. The point of the project is the method, not the discovery.
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

# ---------- Products ----------
catalog = {
    "Electronics":   [("Wireless Earbuds", 1999), ("Smartwatch", 3499), ("Power Bank 20000mAh", 1599),
                      ("Bluetooth Speaker", 2299), ("Phone Case", 399), ("USB-C Cable", 299)],
    "Fashion":       [("Men's T-Shirt", 699), ("Women's Kurti", 1099), ("Sneakers", 2499),
                      ("Denim Jeans", 1799), ("Sports Cap", 449), ("Backpack", 1299)],
    "Home & Kitchen": [("Air Fryer", 4999), ("Mixer Grinder", 3299), ("Bedsheet Set", 1499),
                       ("Water Bottle", 549), ("Storage Boxes", 799), ("LED Desk Lamp", 999)],
    "Beauty":        [("Face Serum", 799), ("Sunscreen SPF50", 499), ("Hair Dryer", 1699),
                      ("Perfume", 1399), ("Lip Balm Set", 349), ("Beard Trimmer", 1299)],
    "Books & Stationery": [("Self-help Book", 349), ("Notebook Pack", 249), ("Fountain Pen", 599),
                           ("Study Planner", 399), ("Coding Handbook", 749), ("Art Supplies Kit", 899)],
}
cost_ratio = {"Electronics": 0.72, "Fashion": 0.55, "Home & Kitchen": 0.65, "Beauty": 0.50, "Books & Stationery": 0.60}
rows, pid = [], 1
for cat, items in catalog.items():
    for name, price in items:
        rows.append((f"P{pid:03d}", name, cat, price, round(price * cost_ratio[cat], 2)))
        pid += 1
products = pd.DataFrame(rows, columns=["product_id", "product_name", "category", "list_price", "unit_cost"])
price_of = products.set_index("product_id")["list_price"].to_dict()
cat_products = {c: products.loc[products.category == c, "product_id"].values for c in catalog}

# ---------- Customers ----------
n_cust = 18000
cities = {"Mumbai": .14, "Delhi": .13, "Bengaluru": .13, "Pune": .09, "Hyderabad": .09,
          "Chennai": .07, "Kolkata": .06, "Ahmedabad": .05, "Jaipur": .04, "Lucknow": .04,
          "Nagpur": .03, "Indore": .03, "Chandigarh": .03, "Kochi": .03, "Aurangabad": .02}
city_names = list(cities)
city_p = np.array(list(cities.values()))
city_p /= city_p.sum()

# 35% were already on the platform before 2024; the rest sign up through the two years
pre = rng.random(n_cust) < 0.35
d_pre = (pd.Timestamp("2022-01-01") + pd.to_timedelta(rng.integers(0, 730, n_cust), unit="D")).values
d_new = (pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 730, n_cust), unit="D")).values
signup = np.where(pre, d_pre, d_new)
customers = pd.DataFrame({
    "customer_id": [f"C{i:05d}" for i in range(1, n_cust + 1)],
    "city": rng.choice(city_names, n_cust, p=city_p),
    "gender": rng.choice(["Male", "Female", "Other"], n_cust, p=[.52, .46, .02]),
    "age": np.clip(rng.normal(30, 8, n_cust).round(), 18, 65).astype(int),
    "signup_date": pd.to_datetime(signup),
    "acquisition_channel": rng.choice(["Organic Search", "Instagram Ads", "Google Ads", "Referral", "Email"],
                                      n_cust, p=[.28, .24, .22, .14, .12]),
})
signup_arr = customers["signup_date"].values

# ---------- Orders ----------
season = {1: 1.10, 2: .90, 3: .95, 4: .90, 5: .92, 6: .85, 7: .88, 8: 1.00, 9: 1.05,
          10: 1.55, 11: 1.35, 12: 1.15}                       # Republic Day sale, Diwali, year-end
dow_w = {0: .95, 1: .92, 2: .95, 3: .98, 4: 1.05, 5: 1.18, 6: 1.15}   # weekend bump
cat_names = list(catalog)
cat_p = [.27, .30, .17, .15, .11]
payment_choices = ["UPI", "Credit Card", "Debit Card", "Cash on Delivery", "Net Banking", "Wallet"]
payment_p = [.38, .17, .14, .20, .06, .05]

days = pd.date_range("2024-01-01", "2025-12-31")
growth = lambda d: 1 + 0.70 * ((d - days[0]).days / len(days))        # business keeps growing
base_orders_per_day = 30

# some customers just shop more than others (lognormal = a few heavy buyers, many light ones)
cust_weight = rng.lognormal(0, 0.7, n_cust)

records, oid = [], 1
for d in days:
    age_days = (np.datetime64(d) - signup_arr) / np.timedelta64(1, "D")
    eligible = age_days >= 0
    # new signups shop soon after joining; interest fades slowly with tenure
    mult = np.where(eligible, 0.5 + 0.5 * np.exp(-np.clip(age_days, 0, None) / 300), 0.0)
    mult = mult * np.where((age_days >= 0) & (age_days < 14), 6.0, 1.0)
    p = cust_weight * mult
    p = p / p.sum()
    n = rng.poisson(base_orders_per_day * season[d.month] * dow_w[d.dayofweek] * growth(d))
    for ci in rng.choice(n_cust, n, p=p):
        cid = customers.at[ci, "customer_id"]
        n_lines = int(rng.choice([1, 2, 3], p=[.72, .20, .08]))
        payment = payment_choices[rng.choice(6, p=payment_p)]
        disc_base = 0.18 if d.month in (10, 11) else 0.08                 # festive months = deeper discounts
        discount_pct = float(np.clip(rng.normal(disc_base, 0.05), 0, 0.45).round(2))
        used = set()
        for _ in range(n_lines):
            cat = cat_names[rng.choice(5, p=cat_p)]
            pr = cat_products[cat][rng.integers(6)]
            if pr in used:                                                # no accidental duplicate lines in one order
                continue
            used.add(pr)
            qty = int(rng.choice([1, 2, 3], p=[.80, .15, .05]))
            p_ret = 0.06                                                  # why people return things:
            if payment == "Cash on Delivery": p_ret += 0.07               #   COD = low commitment
            if cat == "Fashion": p_ret += 0.08                            #   size/fit issues
            if discount_pct > .25: p_ret += 0.03                          #   impulse buys on deep discounts
            records.append((f"O{oid:06d}", d, cid, pr, qty, discount_pct, payment, bool(rng.random() < p_ret)))
        oid += 1

orders = pd.DataFrame(records, columns=["order_id", "order_date", "customer_id", "product_id", "quantity",
                                        "discount_pct", "payment_method", "returned"])
orders["unit_price"] = (orders["product_id"].map(price_of) * (1 - orders["discount_pct"])).round(2)
order_total = (orders["unit_price"] * orders["quantity"]).groupby(orders["order_id"]).transform("sum")
orders["shipping_fee"] = np.where(order_total > 999, 0, 49)               # free shipping above Rs.999
orders["delivery_days"] = np.clip(rng.normal(4.2, 1.6, len(orders)).round(), 1, 12).astype(int)
orders = orders.sort_values(["order_date", "order_id"]).reset_index(drop=True)

# ---------- Make it a little messy (so cleaning is a real step) ----------
dups = orders.sample(frac=0.004, random_state=1)                          # 1) accidental double-logged lines
orders = pd.concat([orders, dups]).sort_values(["order_date", "order_id"]).reset_index(drop=True)
mask = rng.random(len(orders)) < 0.02                                     # 2) inconsistent labels
orders.loc[mask, "payment_method"] = orders.loc[mask, "payment_method"].replace(
    {"UPI": "upi", "Cash on Delivery": "COD", "Credit Card": "credit card"})
orders["delivery_days"] = orders["delivery_days"].astype(float)
orders.loc[rng.random(len(orders)) < 0.015, "delivery_days"] = np.nan     # 3) missing delivery days
customers.loc[rng.random(n_cust) < 0.03, "age"] = np.nan                  # 4) missing ages
customers["age"] = customers["age"].astype("Float64")
mc = rng.random(n_cust) < 0.02
customers.loc[mc, "city"] = customers.loc[mc, "city"] + " "               # 5) stray whitespace

orders.to_csv("data/orders.csv", index=False)
customers.to_csv("data/customers.csv", index=False)
products.to_csv("data/products.csv", index=False)
print(f"orders: {len(orders):,} lines | customers: {len(customers):,} | products: {len(products)}")
