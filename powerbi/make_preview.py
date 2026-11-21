"""
make_preview.py - draws a preview of dashboard page 1 so you can see the target
layout before building it in Power BI.

This is a picture drawn in Python from the SQL results. It is NOT a Power BI
screenshot, and your version will look a little different. Run from the project root:

    python3 powerbi/make_preview.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

SURF, PAGE, INK, INK2, MUTED, GRID = "#fcfcfb", "#f3f2ee", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
BLUE, ORANGE = "#2a78d6", "#eb6834"

q2 = pd.read_csv("sql/results/Q02.csv").iloc[0]
yoy = pd.read_csv("sql/results/Q04.csv")
cat = pd.read_csv("sql/results/Q06.csv")
wk = pd.read_csv("sql/results/Q08.csv")
city = pd.read_csv("sql/results/Q10.csv").head(6)

fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=PAGE)


def panel(x, y, w, h):
    """White card with a soft border. Coordinates are fractions of the page."""
    fig.add_artist(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.006",
                                  transform=fig.transFigure, fc=SURF, ec=GRID, lw=1, zorder=-10))


def ax_in(x, y, w, h):
    ax = fig.add_axes([x, y, w, h], facecolor=SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c3c2b7")
    ax.tick_params(colors=INK2, labelsize=9, length=3)
    return ax


def label(x, y, t, **kw):
    fig.text(x, y, t, **kw)


# ---- header ----
label(0.03, 0.945, "How is the business doing?", fontsize=22, fontweight="bold", color=INK)
label(0.03, 0.905, f"We kept ₹{q2.net_revenue_lakh:,.1f} lakh after returns, at a {q2.profit_margin_pct:.1f}% margin.",
      fontsize=12, color=INK2)

# ---- slicer strip ----
for i, t in enumerate(["Year: All", "Category: All", "City: All", "Payment: All"]):
    x = 0.62 + i * 0.09
    fig.add_artist(FancyBboxPatch((x, 0.915), 0.082, 0.04, boxstyle="round,pad=0,rounding_size=0.01",
                                  transform=fig.transFigure, fc=SURF, ec="#c3c2b7", lw=1))
    label(x + 0.041, 0.935, t + "  ▾", fontsize=9, color=INK2, ha="center", va="center")

# ---- KPI cards ----
kpis = [("Net revenue", f"₹{q2.net_revenue_lakh:,.1f}L"), ("Profit", f"₹{q2.profit_lakh:,.1f}L"),
        ("Profit margin", f"{q2.profit_margin_pct:.1f}%"), ("Orders", f"{int(q2.orders):,}"),
        ("Average order", f"₹{q2.avg_order_value:,.0f}"), ("Items returned", f"{q2.item_return_rate_pct:.1f}%")]
gap = 0.0125
cw = (0.94 - 5 * gap) / 6          # six cards spanning x = 0.03 to 0.97
for i, (name, val) in enumerate(kpis):
    x = 0.03 + i * (cw + gap)
    panel(x, 0.75, cw, 0.11)
    label(x + 0.012, 0.825, name, fontsize=10, color=INK2)
    label(x + 0.012, 0.775, val, fontsize=24, fontweight="bold", color=INK)

# ---- monthly revenue, 2024 vs 2025 ----
panel(0.03, 0.30, 0.56, 0.42)
label(0.043, 0.69, "Sales climb every autumn, and 2025 beat 2024 in every month", fontsize=12, fontweight="bold", color=INK)
label(0.043, 0.665, "Net revenue by month (after returns)", fontsize=9, color=INK2)
ax = ax_in(0.075, 0.34, 0.50, 0.30)
ax.axvspan(9.5, 11.5, color="#f0efec", zorder=0)
ax.plot(yoy.month_num, yoy.y2024_lakh, color=BLUE, lw=2, marker="o", ms=5, mec=SURF, mew=1.5, label="2024")
ax.plot(yoy.month_num, yoy.y2025_lakh, color=ORANGE, lw=2, marker="o", ms=5, mec=SURF, mew=1.5, label="2025")
ax.set_xticks(range(1, 13))
ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
ax.yaxis.set_major_formatter(lambda v, _: f"₹{v:.0f}L")
ax.set_ylim(0)
ax.grid(axis="y", color=GRID, lw=0.8)
ax.set_axisbelow(True)
ax.legend(frameon=False, loc="upper left", labelcolor=INK, fontsize=9)

# ---- category revenue with margin ----
panel(0.60, 0.30, 0.37, 0.42)
label(0.613, 0.69, "Electronics sells most, Beauty keeps most", fontsize=12, fontweight="bold", color=INK)
label(0.613, 0.665, "Net revenue by category, with profit margin on the right", fontsize=9, color=INK2)
ax = ax_in(0.70, 0.34, 0.23, 0.30)
y = range(len(cat))
ax.barh(list(y), cat.net_revenue_lakh, color=BLUE, height=0.6)
ax.set_yticks(list(y))
ax.set_yticklabels(cat.category, fontsize=9)
ax.invert_yaxis()
ax.set_xticks([])
ax.spines["bottom"].set_visible(False)
xmax = cat.net_revenue_lakh.max() * 1.6
ax.set_xlim(0, xmax)
for yi, v, m in zip(y, cat.net_revenue_lakh, cat.margin_pct):
    ax.text(v + 4, yi, f"₹{v:.0f}L", va="center", fontsize=9, color=INK2)
    ax.text(xmax, yi, f"{m:.1f}%", va="center", ha="right", fontsize=10, fontweight="bold", color=INK)
ax.text(xmax, -0.75, "Margin", ha="right", va="center", fontsize=9, color=INK2)

# ---- weekday + cities ----
panel(0.03, 0.04, 0.45, 0.24)
label(0.043, 0.25, "Saturdays and Sundays are the busiest", fontsize=12, fontweight="bold", color=INK)
ax = ax_in(0.06, 0.075, 0.40, 0.14)
ax.bar(wk.weekday, wk.avg_daily_net_revenue / 1e3, color=BLUE, width=0.6)
ax.yaxis.set_major_formatter(lambda v, _: f"₹{v:.0f}K")
ax.grid(axis="y", color=GRID, lw=0.8)
ax.set_axisbelow(True)

panel(0.49, 0.04, 0.48, 0.24)
label(0.503, 0.25, "Five cities bring in about 60% of sales", fontsize=12, fontweight="bold", color=INK)
ax = ax_in(0.56, 0.075, 0.38, 0.14)
ax.barh(list(range(len(city))), city.net_revenue_lakh, color=BLUE, height=0.6)
ax.set_yticks(list(range(len(city))))
ax.set_yticklabels(city.city, fontsize=9)
ax.invert_yaxis()
ax.set_xticks([])
ax.spines["bottom"].set_visible(False)
for yi, v in enumerate(city.net_revenue_lakh):
    ax.text(v + 1.5, yi, f"₹{v:.0f}L", va="center", fontsize=9, color=INK2)
ax.set_xlim(0, city.net_revenue_lakh.max() * 1.2)

label(0.97, 0.012, "Layout preview drawn in Python, not a Power BI screenshot. Yours will look similar.",
      fontsize=8, color=MUTED, ha="right")
fig.savefig("powerbi/dashboard_preview_page1.png", facecolor=PAGE)
print("saved powerbi/dashboard_preview_page1.png")
