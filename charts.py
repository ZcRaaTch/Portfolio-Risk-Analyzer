"""
charts.py
---------
The five charts used in the report. Each function takes the results
dictionary from analytics.run_analysis, draws one chart with Matplotlib,
saves it as a PNG and returns the file path.

Design choices: one consistent colour per stock across every chart, the
portfolio always in black and the benchmark always in dashed grey, light
grid lines, and labels placed directly on the chart where possible.
"""

import os

import matplotlib

matplotlib.use("Agg")  # draw to files; no screen needed
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import MaxNLocator, PercentFormatter

import config
from analytics import PORTFOLIO_NAME

# A colour-blind-checked categorical palette, assigned in a fixed order.
STOCK_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
PORTFOLIO_COLOUR = "#0b0b0b"
BENCHMARK_COLOUR = "#7a7974"
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e6e5e0"

plt.rcParams.update({
    "font.size": 9,
    "axes.edgecolor": INK_2,
    "axes.labelcolor": INK_2,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "legend.frameon": False,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})


def percent_axis(axis):
    """Whole-number percent ticks. Steps of 2.5% are excluded because a tick at
    17.5% would print as a rounded, slightly wrong '18%'."""
    axis.set_major_locator(MaxNLocator(steps=[1, 2, 5, 10]))
    axis.set_major_formatter(PercentFormatter(1.0, decimals=0))


def colour_map(res):
    """Fixed colour for every series, so a stock looks the same in every chart."""
    colours = {name: STOCK_COLOURS[i] for i, name in enumerate(res["weights"].index)}
    colours[PORTFOLIO_NAME] = PORTFOLIO_COLOUR
    colours[config.BENCHMARK_NAME] = BENCHMARK_COLOUR
    return colours


def _save(fig, name, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_cumulative_growth(res, out_dir=config.CHART_DIR):
    """Chart 1: value of Rs 100 invested at the start, for every series."""
    wealth = res["wealth"] * 100
    colours = colour_map(res)
    fig, ax = plt.subplots(figsize=(8, 4.2))

    # Draw stocks first (thin), then benchmark, then portfolio on top (thick).
    order = list(res["weights"].index)
    for name in order:
        ax.plot(wealth.index, wealth[name], color=colours[name], lw=1.2, label=name)
    if res["has_benchmark"]:
        ax.plot(wealth.index, wealth[config.BENCHMARK_NAME], color=BENCHMARK_COLOUR,
                lw=1.8, ls="--", label=config.BENCHMARK_NAME)
    ax.plot(wealth.index, wealth[PORTFOLIO_NAME], color=PORTFOLIO_COLOUR, lw=2.6,
            label=PORTFOLIO_NAME)
    ax.axhline(100, color=INK_2, lw=0.8)

    # Direct label for the portfolio's ending value.
    end_val = wealth[PORTFOLIO_NAME].iloc[-1]
    ax.annotate(f"Rs {end_val:.0f}", (wealth.index[-1], end_val), xytext=(6, 0),
                textcoords="offset points", va="center", fontweight="bold", color=INK)

    # Legend sorted by ending value, so it reads in the same order as the lines.
    handles, labels = ax.get_legend_handles_labels()
    ending = {n: wealth[n].iloc[-1] for n in labels}
    pairs = sorted(zip(handles, labels), key=lambda p: -ending[p[1]])
    ax.legend(*zip(*pairs), loc="upper left", bbox_to_anchor=(1.06, 1), fontsize=8)

    ax.set_title("Growth of Rs 100 invested")
    ax.set_ylabel("Value (Rs)")
    return _save(fig, "01_cumulative_growth.png", out_dir)


def plot_drawdown(res, out_dir=config.CHART_DIR):
    """Chart 2: how far the portfolio was below its previous peak each day."""
    dd = res["drawdowns"]
    m = res["portfolio_mdd"]
    fig, ax = plt.subplots(figsize=(8, 3.4))

    ax.fill_between(dd.index, dd[PORTFOLIO_NAME], 0, color="#86b6ef", alpha=0.35, lw=0)
    ax.plot(dd.index, dd[PORTFOLIO_NAME], color=PORTFOLIO_COLOUR, lw=1.4,
            label=PORTFOLIO_NAME)
    if res["has_benchmark"]:
        ax.plot(dd.index, dd[config.BENCHMARK_NAME], color=BENCHMARK_COLOUR, lw=1.2,
                ls="--", label=config.BENCHMARK_NAME)

    trough = np.datetime64(m["trough_date"])
    ax.scatter([trough], [m["max_drawdown"]], s=40, color=PORTFOLIO_COLOUR, zorder=5,
               edgecolor="white", linewidth=1.5)
    ax.annotate(f"Max drawdown {m['max_drawdown']:.1%}", (trough, m["max_drawdown"]),
                xytext=(8, -4), textcoords="offset points", fontsize=8.5, color=INK)

    percent_axis(ax.yaxis)
    ax.set_ylim(top=0.005)
    ax.set_title("Drawdown: fall from previous peak")
    ax.legend(loc="lower left", fontsize=8)
    return _save(fig, "02_drawdown.png", out_dir)


def plot_risk_return(res, out_dir=config.CHART_DIR):
    """Chart 3: annualised volatility (risk) against annualised return."""
    s = res["summary"]
    colours = colour_map(res)
    fig, ax = plt.subplots(figsize=(7, 4.4))

    points = {}
    for name in s.index:
        x = s.loc[name, "Annualised volatility"]
        y = s.loc[name, "Annualised return (CAGR)"]
        if name == PORTFOLIO_NAME:
            style = dict(marker="D", s=110)
        elif name == config.BENCHMARK_NAME:
            style = dict(marker="s", s=90)
        else:
            style = dict(marker="o", s=80)
        ax.scatter(x, y, color=colours[name], edgecolor="white", linewidth=1.5,
                   zorder=3, **style)
        points[name] = (x, y)

    ax.margins(x=0.18, y=0.15)
    rf = res["rf_annual"]
    ax.axhline(rf, color=INK_2, lw=0.9, ls=":")
    ax.annotate(f"Risk-free rate {rf:.2%}", (0.01, rf), xycoords=("axes fraction", "data"),
                xytext=(0, 4), textcoords="offset points", fontsize=8, color=INK_2)
    ax.axhline(0, color=INK_2, lw=0.8)

    percent_axis(ax.xaxis)
    percent_axis(ax.yaxis)
    ax.set_xlabel("Annualised volatility (risk)")
    ax.set_ylabel("Annualised return (CAGR)")
    ax.set_title("Risk vs return")
    _place_labels(fig, ax, points)
    return _save(fig, "03_risk_return.png", out_dir)


def _place_labels(fig, ax, points):
    """
    Label each point without overlapping other labels or markers.
    Tries the four corners around the point (right-above first) and keeps
    the first position that does not collide with anything already placed.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    to_px = ax.transData.transform
    # Treat every marker as a small box so labels avoid covering points.
    taken = []
    for x, y in points.values():
        px, py = to_px((x, y))
        taken.append((px - 7, py - 7, px + 7, py + 7))

    candidates = [((7, 5), "left", "bottom"), ((7, -5), "left", "top"),
                  ((-7, 5), "right", "bottom"), ((-7, -5), "right", "top")]
    # Place labels for the most crowded points first.
    def crowding(item):
        x, y = to_px(item[1])
        return sum(abs(x - a) + abs(y - b) < 80 for a, b in map(to_px, points.values()))
    for name, (x, y) in sorted(points.items(), key=crowding, reverse=True):
        weight = "bold" if name == PORTFOLIO_NAME else "normal"
        for offset, ha, va in candidates:
            label = ax.annotate(name, (x, y), xytext=offset, textcoords="offset points",
                                ha=ha, va=va, fontsize=8.5, color=INK, fontweight=weight)
            bb = label.get_window_extent(renderer)
            box = (bb.x0 - 2, bb.y0 - 2, bb.x1 + 2, bb.y1 + 2)
            clash = any(box[0] < t[2] and box[2] > t[0] and box[1] < t[3] and box[3] > t[1]
                        for t in taken)
            if not clash or (offset, ha, va) == candidates[-1]:
                taken.append(box)
                break
            label.remove()


def plot_correlation(res, out_dir=config.CHART_DIR):
    """Chart 4: correlation matrix of daily stock returns as a heatmap."""
    corr = res["correlation"]
    # Diverging scale: red for negative, grey at zero, blue for positive.
    cmap = LinearSegmentedColormap.from_list(
        "div", ["#b8322f", "#e34948", "#f0efec", "#2a78d6", "#104281"])
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    im = ax.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1)
    ax.grid(False)

    labels = list(corr.columns)
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9,
                    color="white" if abs(v) > 0.6 else INK)
    for spine in ax.spines.values():
        spine.set_visible(False)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.outline.set_visible(False)
    ax.set_title("Correlation of daily returns")
    return _save(fig, "04_correlation.png", out_dir)


def plot_risk_contribution(res, out_dir=config.CHART_DIR):
    """Chart 5: each stock's capital weight next to its share of portfolio risk."""
    rc = res["risk_contribution"].sort_values("Share of portfolio risk")
    y = np.arange(len(rc))
    h = 0.38
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.barh(y + h / 2, rc["Weight"], height=h, color="#c3c2b7", label="Capital weight")
    ax.barh(y - h / 2, rc["Share of portfolio risk"], height=h, color="#2a78d6",
            label="Share of portfolio risk")
    for i, (w, r) in enumerate(zip(rc["Weight"], rc["Share of portfolio risk"])):
        ax.text(w + 0.004, i + h / 2, f"{w:.0%}", va="center", fontsize=8, color=INK_2)
        ax.text(r + 0.004, i - h / 2, f"{r:.1%}", va="center", fontsize=8, color=INK)
    ax.set_yticks(y, rc.index)
    percent_axis(ax.xaxis)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(rc["Share of portfolio risk"].max(), 0.2) * 1.18)
    ax.set_title("Capital weight vs share of portfolio risk")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=8)
    return _save(fig, "05_risk_contribution.png", out_dir)


def make_all_charts(res, out_dir=config.CHART_DIR):
    """Draw every chart and return {short name: file path}."""
    return {
        "growth": plot_cumulative_growth(res, out_dir),
        "drawdown": plot_drawdown(res, out_dir),
        "risk_return": plot_risk_return(res, out_dir),
        "correlation": plot_correlation(res, out_dir),
        "risk_contribution": plot_risk_contribution(res, out_dir),
    }
