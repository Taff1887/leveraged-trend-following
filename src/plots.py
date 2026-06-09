"""
plots.py
========

All charting lives here so the figures share one consistent style and every plot
is saved to ``charts/`` automatically. Each function builds one figure, saves it
as a PNG, and returns the Matplotlib figure so notebooks can display it inline.

Nothing here computes statistics -- the functions just visualise series that the
other modules produce. This keeps plotting separate from logic.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import seaborn as sns
    _HAS_SNS = True
except Exception:  # seaborn is optional
    _HAS_SNS = False

from . import config
from .metrics import drawdown_series, rolling_cagr, rolling_sharpe
from .signals import moving_average, signal_segments, trend_signal


# ---------------------------------------------------------------------------
# Style + saving
# ---------------------------------------------------------------------------
def setup_style() -> None:
    """Apply the project's matplotlib style. Safe to call many times."""
    try:
        plt.style.use(config.CHART_STYLE)
    except Exception:
        plt.style.use("ggplot")
    plt.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": config.CHART_DPI,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "figure.titlesize": 14,
        "figure.titleweight": "bold",
        "legend.frameon": True,
        "legend.framealpha": 0.9,
    })


def save_fig(fig, filename: str) -> Path:
    """Save ``fig`` to ``charts/filename`` and return the path."""
    path = config.CHARTS_DIR / filename
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    return path


# ---------------------------------------------------------------------------
# Part 1: cumulative return
# ---------------------------------------------------------------------------
def plot_cumulative(series_dict: dict, title: str, filename: str,
                    log: bool = True, ylabel: str = "Growth of $1") -> plt.Figure:
    """Plot one or more equity / index curves (rebased to start at 1.0)."""
    setup_style()
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for i, (name, s) in enumerate(series_dict.items()):
        s = s.dropna()
        rebased = s / s.iloc[0]
        ax.plot(rebased.index, rebased.values, label=name, linewidth=1.4)
    if log:
        ax.set_yscale("log")
        ax.set_ylabel(ylabel + " (log scale)")
    else:
        ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.legend(loc="upper left")
    return fig


# ---------------------------------------------------------------------------
# Part 2: moving-average signal chart
# ---------------------------------------------------------------------------
def plot_ma_signal(prices: pd.Series, window: int, filename: str,
                   title: str | None = None, log: bool = True) -> plt.Figure:
    """Price + its moving average, with the BELOW-MA periods shaded.

    The shaded regions are exactly when our leveraged strategy switches on its
    extra exposure, so this chart shows 'where the action is'.
    """
    setup_style()
    prices = prices.dropna()
    sma = moving_average(prices, window)
    sig = trend_signal(prices, window)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(prices.index, prices.values, color=config.COLORS["buy_hold"],
            linewidth=1.0, label="S&P 500 TR index")
    ax.plot(sma.index, sma.values, color=config.COLORS["accent"],
            linewidth=1.3, label=f"{window}-day SMA")

    # Shade the BELOW-MA segments (signal == 0).
    for start, end, val in signal_segments(sig):
        if val == 0:
            ax.axvspan(start, end, color=config.COLORS["leveraged"], alpha=0.10)
    # One proxy patch for the legend.
    ax.axvspan(prices.index[0], prices.index[0], color=config.COLORS["leveraged"],
               alpha=0.10, label="Below MA (leverage on)")

    if log:
        ax.set_yscale("log")
    ax.set_title(title or f"S&P 500 TR vs {window}-day moving average")
    ax.set_xlabel("Date")
    ax.set_ylabel("Index level (log scale)" if log else "Index level")
    ax.legend(loc="upper left")
    return fig


# ---------------------------------------------------------------------------
# Equity-curve comparison
# ---------------------------------------------------------------------------
def plot_equity_comparison(equity_dict: dict, title: str, filename: str,
                           log: bool = True, colors: dict | None = None) -> plt.Figure:
    """Compare several strategies' equity curves on one chart."""
    setup_style()
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for name, eq in equity_dict.items():
        eq = eq.dropna()
        rebased = eq / eq.iloc[0]
        c = (colors or {}).get(name)
        ax.plot(rebased.index, rebased.values, label=name, linewidth=1.5, color=c)
    if log:
        ax.set_yscale("log")
        ax.set_ylabel("Growth of $1 (log scale)")
    else:
        ax.set_ylabel("Growth of $1")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.legend(loc="upper left")
    return fig


# ---------------------------------------------------------------------------
# Drawdown comparison
# ---------------------------------------------------------------------------
def plot_drawdowns(returns_dict: dict, title: str, filename: str,
                   colors: dict | None = None) -> plt.Figure:
    """Underwater (drawdown) chart for several strategies."""
    setup_style()
    fig, ax = plt.subplots(figsize=(11, 5.0))
    for name, rets in returns_dict.items():
        dd = drawdown_series(rets.dropna()) * 100.0
        c = (colors or {}).get(name)
        ax.plot(dd.index, dd.values, label=name, linewidth=1.2, color=c)
        ax.fill_between(dd.index, dd.values, 0, alpha=0.08, color=c)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown (%)")
    ax.legend(loc="lower left")
    return fig


# ---------------------------------------------------------------------------
# Rolling statistics
# ---------------------------------------------------------------------------
def plot_rolling_returns(returns_dict: dict, years: int, title: str,
                         filename: str, colors: dict | None = None) -> plt.Figure:
    """Rolling annualized return over a ``years``-year window."""
    setup_style()
    fig, ax = plt.subplots(figsize=(11, 5.0))
    for name, rets in returns_dict.items():
        rc = rolling_cagr(rets.dropna(), years=years) * 100.0
        c = (colors or {}).get(name)
        ax.plot(rc.index, rc.values, label=name, linewidth=1.2, color=c)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel(f"Rolling {years}-year annualized return (%)")
    ax.legend(loc="lower left")
    return fig


def plot_rolling_sharpe(returns_dict: dict, years: int, title: str,
                        filename: str, colors: dict | None = None) -> plt.Figure:
    """Rolling annualized Sharpe ratio over a ``years``-year window."""
    setup_style()
    fig, ax = plt.subplots(figsize=(11, 5.0))
    for name, rets in returns_dict.items():
        rs = rolling_sharpe(rets.dropna(), years=years)
        c = (colors or {}).get(name)
        ax.plot(rs.index, rs.values, label=name, linewidth=1.2, color=c)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel(f"Rolling {years}-year Sharpe")
    ax.legend(loc="lower left")
    return fig


# ---------------------------------------------------------------------------
# Generic heatmap (used by the parameter sweep and Monte Carlo)
# ---------------------------------------------------------------------------
def plot_heatmap(matrix: pd.DataFrame, title: str, filename: str,
                 fmt: str = ".2f", cmap: str = "RdYlGn", center=None,
                 xlabel: str = "", ylabel: str = "", annot: bool = True,
                 cbar_label: str = "") -> plt.Figure:
    """Annotated heatmap from a DataFrame (rows = y-axis, columns = x-axis)."""
    setup_style()
    fig, ax = plt.subplots(figsize=(1.2 * matrix.shape[1] + 3,
                                    0.6 * matrix.shape[0] + 2.5))
    if _HAS_SNS:
        sns.heatmap(matrix, annot=annot, fmt=fmt, cmap=cmap, center=center,
                    ax=ax, cbar_kws={"label": cbar_label}, linewidths=0.5,
                    linecolor="white")
    else:  # matplotlib fallback
        im = ax.imshow(matrix.values, cmap=cmap, aspect="auto")
        ax.set_xticks(range(matrix.shape[1]))
        ax.set_xticklabels(matrix.columns, rotation=45, ha="right")
        ax.set_yticks(range(matrix.shape[0]))
        ax.set_yticklabels(matrix.index)
        fig.colorbar(im, ax=ax, label=cbar_label)
        if annot:
            for i in range(matrix.shape[0]):
                for j in range(matrix.shape[1]):
                    ax.text(j, i, format(matrix.values[i, j], fmt),
                            ha="center", va="center", fontsize=8)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    return fig


# ---------------------------------------------------------------------------
# ETF comparison
# ---------------------------------------------------------------------------
def plot_synthetic_vs_real(curves: dict, title: str, filename: str) -> plt.Figure:
    """Overlay synthetic-leverage equity curves against real leveraged-ETF curves."""
    setup_style()
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for name, eq in curves.items():
        eq = eq.dropna()
        rebased = eq / eq.iloc[0]
        style = "--" if "synthetic" in name.lower() else "-"
        ax.plot(rebased.index, rebased.values, style, label=name, linewidth=1.5)
    ax.set_yscale("log")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Growth of $1 (log scale)")
    ax.legend(loc="upper left")
    return fig


# ---------------------------------------------------------------------------
# Volatility-decay teaching chart
# ---------------------------------------------------------------------------
def plot_vol_decay_example(filename: str = "volatility_decay_example.png") -> plt.Figure:
    """A simple two-panel teaching figure for volatility decay.

    Left: a choppy, flat market (+10%/-10% repeating) where leverage LOSES money.
    Right: a smooth uptrend where leverage HELPS. Same daily-leverage mechanics.
    """
    setup_style()
    levs = [1.0, 2.0, 3.0]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Left: choppy market, alternating +10% / -10% for 40 days.
    chop = np.array([0.10, -0.10] * 20)
    for L in levs:
        eq = np.cumprod(1.0 + L * chop)
        ax1.plot(range(1, len(eq) + 1), eq, marker="o", markersize=2.5,
                 label=f"{L:g}x")
    ax1.axhline(1.0, color="black", linewidth=0.8, linestyle=":")
    ax1.set_title("Choppy flat market (+10%/-10%): leverage DECAYS")
    ax1.set_xlabel("Day")
    ax1.set_ylabel("Growth of $1")
    ax1.legend()

    # Right: smooth uptrend, +0.4% per day for 40 days.
    trend = np.full(40, 0.004)
    for L in levs:
        eq = np.cumprod(1.0 + L * trend)
        ax2.plot(range(1, len(eq) + 1), eq, marker="o", markersize=2.5,
                 label=f"{L:g}x")
    ax2.axhline(1.0, color="black", linewidth=0.8, linestyle=":")
    ax2.set_title("Smooth uptrend (+0.4%/day): leverage HELPS")
    ax2.set_xlabel("Day")
    ax2.set_ylabel("Growth of $1")
    ax2.legend()

    fig.suptitle("Volatility decay: the SAME daily leverage helps or hurts "
                 "depending on the path", y=1.02)
    return fig
