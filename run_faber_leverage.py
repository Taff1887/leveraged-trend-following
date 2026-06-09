"""
run_faber_leverage.py
=====================

The "v2" analysis requested after reading Faber (2013) closely. It does four
things, faithfully following the paper's monthly 10-month methodology and then
extending it to leverage:

  Step 0  Faber replication  -- monthly S&P 500 total return back to 1901,
                                10-month SMA -> cash (90-day T-bills). Validate
                                against Faber's published numbers.
  Step 1  Longest baseline    -- daily total return (~1928+), 200-day SMA -> cash.
  Step 2  Leverage the index  -- daily 1.5x / 2.5x / 3x on the index, vs timing.
  Step 3  Optimal leverage    -- closed-form + Monte Carlo: the break-even and
                                growth-optimal (Kelly) leverage as functions of
                                trend and volatility.
  Step 4  Inverted strategy   -- LEVERAGE ABOVE the MA, 1x below (the volatility-
                                aware mirror image). 1.5x / 2x / 3x vs buy&hold
                                and vs Faber's move-to-cash.

Outputs go to results/ (prefix "faber_") and charts/ (prefix "F").
Run:  python run_faber_leverage.py
"""

from __future__ import annotations

import json
import re
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from src import config
from src import long_history as lh
from src import returns as rt
from src import signals as sg
from src import backtest as bt
from src import metrics as mx
from src import plots as pl
from src import monte_carlo as mc

H = {}


def save_table(df, name, index=False):
    df.to_csv(config.RESULTS_DIR / name, index=index)
    print(f"    table -> results/{name} ({len(df)} rows)")


def save_chart(fig, name):
    pl.save_fig(fig, name); plt.close(fig)
    print(f"    chart -> charts/{name}")


def r4(x):
    try:
        return round(float(x), 4)
    except (TypeError, ValueError):
        return x


def metrics_row(name, returns, rf, pp, extra=None):
    s = mx.summarize(returns, rf_daily=rf, name=name, periods_per_year=pp)
    row = {"name": name, "cagr": s["cagr"], "volatility": s["volatility"],
           "sharpe": s["sharpe"], "sortino": s["sortino"],
           "max_drawdown": s["max_drawdown"], "calmar": s["calmar"],
           "total_return": s["total_return"], "years": s["years"]}
    if extra:
        row.update(extra)
    return row


def period_metrics(name, returns, rf, start, tag=None):
    """metrics_row but restricted to dates >= ``start`` (daily series)."""
    r = returns[returns.index >= pd.Timestamp(start)].dropna()
    rfx = rf.reindex(r.index) if hasattr(rf, "reindex") else rf
    return metrics_row(name, r, rfx, 252, {"strategy": tag} if tag else None)


# The leverage levels we test everywhere.
LEVS = [1.5, 2.0, 3.0, 4.0]

# Per-leverage colours so the same level looks the same across every chart.
_LEVCOL = {"1.5": "#ff7f0e", "2": "#d62728", "3": "#9467bd", "4": "#8c564b"}

# Horizons used for the per-strategy breakdown (0 = full history).
HORIZONS = [("full (1928+)", 0), ("last 50y", 50), ("last 30y", 30), ("last 15y", 15)]


def color_for(name: str):
    """Pick a consistent colour for a strategy by its name / leverage level."""
    if name.startswith("Buy & Hold"):
        return config.COLORS["buy_hold"]
    m = re.search(r"(\d+(?:\.\d+)?)x", name)
    if m and m.group(1) in _LEVCOL:
        return _LEVCOL[m.group(1)]
    if "Cash" in name:
        return config.COLORS["ma_cash"]
    return None


def strat_table(strats: dict, rf_d, bench=None) -> pd.DataFrame:
    """Metrics table for a dict of {name: daily net-return Series}.

    If ``bench`` (the S&P 500 / buy-and-hold daily returns) is given, an
    information ratio versus that benchmark is added.
    """
    rows = []
    for name, r in strats.items():
        r = r.dropna()
        rfx = rf_d.reindex(r.index)
        ir = mx.information_ratio(r, bench) if bench is not None else np.nan
        rows.append({"name": name,
                     "grew_1dollar_to": float((1.0 + r).prod()),
                     "cagr": mx.cagr(r), "volatility": mx.annual_volatility(r),
                     "sharpe": mx.sharpe_ratio(r, rfx),
                     "sortino": mx.sortino_ratio(r, rfx),
                     "calmar": mx.calmar_ratio(r),
                     "max_drawdown": mx.max_drawdown(r),
                     "info_ratio_vs_sp": ir})
    return pd.DataFrame(rows)


def equity_chart(strats: dict, title: str, fname: str, styles: dict | None = None):
    """Equity-curve chart for a dict of {name: net-return Series}, $-axis."""
    curves = {name: rt.cumulative_index(r.dropna()) for name, r in strats.items()}
    colors = {name: color_for(name) for name in strats}
    fig = pl.plot_equity_comparison(curves, title, fname, colors=colors, styles=styles)
    save_chart(fig, fname)


def horizon_analysis(strats: dict, family: str, prefix: str, rf_d, last) -> pd.DataFrame:
    """Run a strategy set over full / 50y / 30y / 15y: one combined metrics table
    (with Sortino + information ratio vs the S&P) and one equity chart per horizon.

    ``strats`` must include "Buy & Hold 1x" (used as the S&P benchmark for IR).
    """
    bench_full = strats["Buy & Hold 1x"]
    tables = []
    for hlabel, yrs in HORIZONS:
        start = None if yrs == 0 else last - pd.Timedelta(days=365 * yrs)
        sub = {n: (r if start is None else r[r.index >= start]) for n, r in strats.items()}
        bench = bench_full if start is None else bench_full[bench_full.index >= start]
        t = strat_table(sub, rf_d, bench=bench)
        t.insert(0, "horizon", hlabel)
        tables.append(t)
        tag = "full" if yrs == 0 else f"{yrs}y"
        equity_chart(sub, f"{family} -- {hlabel}", f"{prefix}_{tag}.png")
    full = pd.concat(tables, ignore_index=True)
    save_table(full, f"faber_{prefix}_horizons.csv")
    H[prefix + "_horizons"] = {h: table_to_headline(full[full["horizon"] == h])
                               for h in full["horizon"].unique()}
    return full


# ===========================================================================
# Step 0: Faber monthly replication
# ===========================================================================
def step0_faber(monthly_idx, rf_m):
    print("[step 0] Faber monthly replication (10-month SMA -> cash) ...")
    r = rt.simple_returns(monthly_idx)
    bh = bt.buy_and_hold(r, rf_daily=rf_m, name="S&P 500 (buy & hold)")
    sig = sg.monthly_trend_signal(monthly_idx, 10).reindex(r.index)
    tim = bt.run_exposure_strategy(r, sig, rf_daily=rf_m,
                                   name="10-month timing -> cash")
    rows = [metrics_row(bh.name, bh.net_returns, rf_m, 12),
            metrics_row(tim.name, tim.net_returns, rf_m, 12,
                        {"pct_in_market": float((tim.exposure > 0).mean())})]
    tbl = pd.DataFrame(rows)
    save_table(tbl, "faber_step0_monthly_replication.csv")

    H["step0_faber_replication"] = {
        "sample": f"{r.index.min().date()} to {r.index.max().date()}",
        "buy_hold": {k: r4(rows[0][k]) for k in ("cagr", "volatility", "sharpe", "max_drawdown")},
        "timing": {k: r4(rows[1][k]) for k in ("cagr", "volatility", "sharpe", "max_drawdown")},
        "faber_published": {"sp_compound": 0.0932, "timing_compound": 0.1018,
                            "sp_maxdd": -0.8366, "timing_maxdd": -0.4224},
    }
    fig = pl.plot_equity_comparison(
        {"S&P 500 (buy & hold)": bh.equity, "10-month timing -> cash": tim.equity},
        "Step 0 — Faber replication: S&P 500 vs 10-month timing (monthly, 1901+)",
        "F0_faber_replication.png",
        colors={"S&P 500 (buy & hold)": config.COLORS["buy_hold"],
                "10-month timing -> cash": config.COLORS["ma_cash"]})
    save_chart(fig, "F0_faber_replication.png")
    return bh, tim


# ===========================================================================
# Step 1: longest daily baseline
# ===========================================================================
def step1_baseline(daily_idx, rf_d):
    print("[step 1] longest daily baseline (200-day SMA -> cash) ...")
    u = rt.simple_returns(daily_idx)
    bh = bt.buy_and_hold(u, rf_daily=rf_d, name="Buy & Hold 1x")
    ma = bt.ma_to_cash(daily_idx, u, 200, rf_daily=rf_d)
    rows = [metrics_row("Buy & Hold 1x", bh.net_returns, rf_d, 252),
            metrics_row("MA200 -> Cash", ma.net_returns, rf_d, 252,
                        {"pct_in_market": float((ma.exposure > 0).mean())})]
    save_table(pd.DataFrame(rows), "faber_step1_daily_baseline.csv")
    H["step1_daily_baseline"] = {
        "sample": f"{u.index.min().date()} to {u.index.max().date()}",
        "buy_hold": {k: r4(rows[0][k]) for k in ("cagr", "volatility", "sharpe", "max_drawdown", "calmar")},
        "ma200_cash": {k: r4(rows[1][k]) for k in ("cagr", "volatility", "sharpe", "max_drawdown", "calmar")},
    }
    colors = {"Buy & Hold 1x": config.COLORS["buy_hold"], "MA200 -> Cash": config.COLORS["ma_cash"]}
    fig = pl.plot_equity_comparison(
        {"Buy & Hold 1x": bh.equity, "MA200 -> Cash": ma.equity},
        "Step 1 — Buy & Hold vs the 200-day MA rule (S&P 500 total return, 1928+)",
        "F1_baseline_equity.png", colors=colors)
    save_chart(fig, "F1_baseline_equity.png")
    fig = pl.plot_drawdowns(
        {"Buy & Hold 1x": bh.net_returns, "MA200 -> Cash": ma.net_returns},
        "Step 1 — Drawdowns: Buy & Hold vs the 200-day MA rule",
        "F1_baseline_drawdowns.png", colors=colors)
    save_chart(fig, "F1_baseline_drawdowns.png")
    return bh, ma, u


# ===========================================================================
# Step 2: daily leverage on the index
# ===========================================================================
def step2_leverage_index(daily_idx, u, rf_d, bh, ma):
    print("[step 2] daily leverage on the index (constant) ...")
    levs = LEVS
    results = {L: bt.always_leveraged(u, L, rf_daily=rf_d, costs=config.DEFAULT_COSTS)
               for L in levs}
    rows = [metrics_row("Buy & Hold 1x", bh.net_returns, rf_d, 252),
            metrics_row("MA200 -> Cash", ma.net_returns, rf_d, 252)]
    for L in levs:
        rows.append(metrics_row(f"Always {L:g}x (daily, net)", results[L].net_returns, rf_d, 252))
    save_table(pd.DataFrame(rows), "faber_step2_leverage_index.csv")

    curves = {"Buy & Hold 1x": bh.equity, "MA200 -> Cash": ma.equity}
    curves.update({f"Always {L:g}x": results[L].equity for L in levs})
    fig = pl.plot_equity_comparison(
        curves, "Step 2 — Daily-leveraged S&P 500 index vs timing (net of costs)",
        "F2_leverage_on_index.png")
    save_chart(fig, "F2_leverage_on_index.png")
    H["step2_leverage_index"] = {f"always_{L:g}x_cagr": r4(mx.cagr(results[L].net_returns))
                                 for L in levs}


# ===========================================================================
# Step 3: optimal-leverage surfaces (closed form + Monte Carlo)
# ===========================================================================
def step3_surfaces(u, rf_d):
    print("[step 3] optimal-leverage surfaces ...")
    drifts = config.MC_ANNUAL_DRIFTS
    vols = config.MC_ANNUAL_VOLS

    # Closed-form Kelly (growth-optimal) and break-even (same return as 1x).
    kelly = mc.closed_form_leverage_grids(drifts, vols, "kelly").clip(0, 6)
    be = mc.closed_form_leverage_grids(drifts, vols, "breakeven").clip(0, 8)
    kelly.index = [f"{v:.0%}" for v in kelly.index]; kelly.columns = [f"{d:.0%}" for d in kelly.columns]
    be.index = [f"{v:.0%}" for v in be.index]; be.columns = [f"{d:.0%}" for d in be.columns]

    fig = pl.plot_heatmap(kelly, "Growth-optimal (Kelly) leverage  L* = drift / vol²",
                          "F3_kelly_leverage.png", fmt=".2g", cmap="viridis",
                          xlabel="Annual EXCESS drift", ylabel="Annual volatility",
                          cbar_label="Optimal leverage")
    save_chart(fig, "F3_kelly_leverage.png")
    fig = pl.plot_heatmap(be, "Break-even leverage  L = 2·drift/vol² − 1  (same CAGR as 1x)",
                          "F3_breakeven_leverage.png", fmt=".2g", cmap="magma",
                          xlabel="Annual EXCESS drift", ylabel="Annual volatility",
                          cbar_label="Break-even leverage")
    save_chart(fig, "F3_breakeven_leverage.png")

    # S&P-like point: arithmetic excess drift and vol from the long daily TR.
    rf_ann = float((1 + rf_d.reindex(u.index).fillna(0)).prod() **
                   (config.TRADING_DAYS_PER_YEAR / len(u)) - 1)
    mu_arith = float(u.mean() * config.TRADING_DAYS_PER_YEAR)
    sigma = float(u.std(ddof=1) * np.sqrt(config.TRADING_DAYS_PER_YEAR))
    mu_excess = mu_arith - rf_ann
    kelly_sp = mu_excess / sigma ** 2
    be_sp = 2 * mu_excess / sigma ** 2 - 1
    print(f"    S&P-like: excess drift={mu_excess:.3f}, vol={sigma:.3f}, "
          f"Kelly={kelly_sp:.2f}, break-even={be_sp:.2f}")

    # Monte Carlo validation: median CAGR vs leverage at the S&P-like point.
    fine_levs = list(np.round(np.arange(1.0, 5.01, 0.25), 2))
    grid = mc.run_grid(drifts=[round(mu_excess, 3)], vols=[round(sigma, 3)],
                       leverages=fine_levs, horizons_years=[10], n_paths=4000,
                       verbose=False)
    g10 = grid[grid.horizon_years == 10]
    closed = mu_excess * np.array(fine_levs) - 0.5 * (np.array(fine_levs) ** 2) * sigma ** 2

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(g10.leverage, g10.median_cagr * 100, "o-", color=config.COLORS["leveraged"],
            label="Monte Carlo median CAGR")
    ax.plot(fine_levs, closed * 100, "--", color="black",
            label="Closed form  L·μ − ½L²σ²")
    ax.axhline(g10[g10.leverage == 1.0].median_cagr.iloc[0] * 100, color="grey",
               ls=":", label="1x level")
    ax.axvline(kelly_sp, color=config.COLORS["ma_cash"], ls="--",
               label=f"Kelly L*={kelly_sp:.2f}")
    ax.axvline(be_sp, color=config.COLORS["accent"], ls="--",
               label=f"Break-even L={be_sp:.2f}")
    ax.set_xlabel("Leverage"); ax.set_ylabel("10-yr median CAGR (%)")
    ax.set_title("Step 3 — Optimal leverage at the S&P-like point\n"
                 f"(excess drift {mu_excess:.1%}, vol {sigma:.1%}): "
                 "growth peaks at Kelly, ties 1x at break-even")
    ax.legend(fontsize=8)
    save_chart(fig, "F3_optimal_leverage_curve.png")

    H["step3_surfaces"] = {
        "sp_excess_drift": r4(mu_excess), "sp_vol": r4(sigma),
        "kelly_leverage": r4(kelly_sp), "breakeven_leverage": r4(be_sp),
        "note": "iid model; real fat tails / vol-clustering lower the realised optimum",
    }


# ===========================================================================
# Step 3b: the "what leverage matches the S&P?" contour map
# ===========================================================================
def step3b_breakeven_chart(u, rf_d):
    """A volatility-vs-trend map whose value is the BREAK-EVEN daily leverage:
    the leverage whose compound return exactly TIES 1x. Below the contour leverage
    helps; above it, volatility decay makes leverage LOSE relative to 1x."""
    print("[step 3b] break-even leverage contour map ...")
    drifts = np.linspace(0.0, 0.15, 76)   # annual EXCESS arithmetic drift (over cash)
    vols = np.linspace(0.05, 0.60, 76)    # annual volatility
    D, V = np.meshgrid(drifts, vols)
    L_be = np.clip(2.0 * D / V ** 2 - 1.0, 0.0, 5.0)   # break-even leverage

    # The S&P's own point, from the long daily series.
    rf_ann = float((1 + rf_d.reindex(u.index).fillna(0)).prod() **
                   (config.TRADING_DAYS_PER_YEAR / len(u)) - 1)
    mu_ex = float(u.mean() * config.TRADING_DAYS_PER_YEAR) - rf_ann
    sigma = float(u.std(ddof=1) * np.sqrt(config.TRADING_DAYS_PER_YEAR))

    pl.setup_style()
    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    cf = ax.contourf(D * 100, V * 100, L_be, levels=np.linspace(0, 5, 26),
                     cmap="RdYlGn", extend="max")
    # Labelled contour lines at the leverage levels people actually consider.
    lines = ax.contour(D * 100, V * 100, L_be,
                       levels=[1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0],
                       colors="black", linewidths=1.0)
    ax.clabel(lines, fmt=lambda x: f"{x:g}x", fontsize=9)
    # The "even 1x is too much" frontier (break-even leverage < 1).
    ax.contour(D * 100, V * 100, L_be, levels=[1.0], colors="black", linewidths=2.6)

    ax.plot(mu_ex * 100, sigma * 100, marker="*", color="black", markersize=22,
            markeredgecolor="white", zorder=5)
    ax.annotate(f"S&P 500\n(excess drift {mu_ex:.1%}, vol {sigma:.0%})\n"
                f"break-even ≈ {2*mu_ex/sigma**2-1:.1f}x, Kelly ≈ {mu_ex/sigma**2:.1f}x",
                xy=(mu_ex * 100, sigma * 100), xytext=(mu_ex * 100 + 2, sigma * 100 + 9),
                fontsize=9, color="black",
                arrowprops=dict(arrowstyle="->", color="black"),
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.85))
    cbar = fig.colorbar(cf, ax=ax)
    cbar.set_label("Break-even daily leverage (the level that exactly ties 1x)")
    ax.set_xlabel("Annual trend  (excess drift over cash, %)")
    ax.set_ylabel("Annual volatility (%)")
    ax.set_title("What daily leverage matches the S&P?\n"
                 "On/below the labelled contour, leverage MATCHES or beats 1x; "
                 "above it, volatility decay makes leverage LOSE")
    save_chart(fig, "F3_breakeven_leverage_map.png")


# ===========================================================================
# Step 3c: the "flat total return" leverage map (volatility decay vs trend)
# ===========================================================================
def step3c_zero_return_map(u):
    """Map of the ZERO-RETURN leverage: the daily leverage at which volatility
    decay exactly cancels the trend, so the long-run TOTAL compound return is 0.

    In terms of the 1x compound return g (CAGR) and volatility sigma,
        leveraged CAGR(L) = 0  =>  L_zero = 2*g/sigma^2 + 1.
    Below L_zero leverage still grows; above it, decay wins and you LOSE money;
    far above it you are effectively wiped out (terminal wealth -> 0).
    """
    print("[step 3c] zero-return (flat) leverage map ...")
    # S&P marker: realised CAGR & volatility over the LAST ~10 years.
    last10 = u[u.index >= (u.index.max() - pd.Timedelta(days=3653))]
    g_sp = mx.cagr(last10)
    sig_sp = mx.annual_volatility(last10)
    Lzero_sp = 2 * g_sp / sig_sp ** 2 + 1

    cagrs = np.linspace(0.0, 0.20, 81)   # 1x CAGR ("trend")
    vols = np.linspace(0.05, 0.60, 81)
    G, V = np.meshgrid(cagrs, vols)
    Lzero = np.clip(2.0 * G / V ** 2 + 1.0, 1.0, 15.0)

    pl.setup_style()
    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    cf = ax.contourf(G * 100, V * 100, Lzero, levels=np.linspace(1, 15, 29),
                     cmap="RdYlGn", extend="max")
    lines = ax.contour(G * 100, V * 100, Lzero,
                       levels=[2, 3, 4, 5, 7, 10, 13], colors="black", linewidths=1.0)
    ax.clabel(lines, fmt=lambda x: f"{x:g}x", fontsize=9)
    ax.plot(g_sp * 100, sig_sp * 100, marker="*", color="black", markersize=22,
            markeredgecolor="white", zorder=5)
    ax.annotate(f"S&P 500 (last 10y)\nCAGR {g_sp:.1%}, vol {sig_sp:.0%}\n"
                f"flat-return leverage ≈ {Lzero_sp:.1f}x",
                xy=(g_sp * 100, sig_sp * 100), xytext=(g_sp * 100 - 6.5, sig_sp * 100 + 11),
                fontsize=9, arrowprops=dict(arrowstyle="->", color="black"),
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.85))
    fig.colorbar(cf, ax=ax).set_label("Zero-return daily leverage (total compound return = 0)")
    ax.set_xlabel("Annual trend  (1x CAGR, %)")
    ax.set_ylabel("Annual volatility (%)")
    ax.set_title("Where volatility decay eats the whole trend\n"
                 "Leverage at the contour gives 0% total return; above it, "
                 "leverage LOSES money (e.g. ~10x flattens the recent S&P)")
    save_chart(fig, "F3_zero_return_leverage_map.png")

    H["step3c_zero_return"] = {"sp_last10_cagr": r4(g_sp), "sp_last10_vol": r4(sig_sp),
                               "sp_zero_return_leverage": r4(Lzero_sp)}


# ===========================================================================
# Step 5: buying leverage at crisis lows (does timing the bottom work?)
# ===========================================================================
def step5_event_studies(daily_idx, u):
    """Forward total return from major market BOTTOMS for 1x / 1.5x / 2x / 3x
    (synthetic daily leverage). Shows leverage pays HUGELY if you buy the exact
    low -- the catch being that you cannot know the low in real time."""
    print("[step 5] buying leverage at crisis lows ...")
    windows = [("GFC bottom (2009)", "2008-09-01", "2009-12-31"),
               ("2018 Q4 selloff", "2018-10-01", "2019-01-31"),
               ("COVID bottom (2020)", "2020-02-01", "2020-07-31"),
               ("2025 tariff selloff", "2025-01-01", "2025-12-31")]
    levs = [1.0] + LEVS
    horizons = [("6mo", 126), ("1yr", 252), ("3yr", 756)]

    rows = []
    for label, s, e in windows:
        seg = daily_idx[(daily_idx.index >= pd.Timestamp(s)) & (daily_idx.index <= pd.Timestamp(e))]
        if seg.empty:
            continue
        low_date = seg.idxmin()
        fwd = u[u.index > low_date]
        for hl, hd in horizons:
            if len(fwd) < hd:
                continue
            wr = fwd.iloc[:hd]
            row = {"event": label, "low_date": str(low_date.date()), "horizon": hl}
            for L in levs:
                row[f"{L:g}x"] = float((1.0 + L * wr).cumprod().iloc[-1] - 1.0)
            rows.append(row)
    tbl = pd.DataFrame(rows)
    save_table(tbl, "faber_step5_buy_leverage_at_lows.csv")

    # Grouped bar chart at the 1-year horizon.
    one = tbl[tbl["horizon"] == "1yr"].reset_index(drop=True)
    if len(one):
        pl.setup_style()
        fig, ax = plt.subplots(figsize=(11, 5.8))
        x = np.arange(len(one)); n = len(levs); width = 0.8 / n
        for i, L in enumerate(levs):
            off = (i - (n - 1) / 2.0) * width
            ax.bar(x + off, one[f"{L:g}x"] * 100, width, label=f"{L:g}x",
                   color=color_for(f"{L:g}x"))
        ax.set_xticks(x); ax.set_xticklabels(one["event"], fontsize=9)
        ax.set_ylabel("1-year forward total return (%)")
        ax.axhline(0, color="black", lw=0.8)
        ax.set_title("If you BUY leverage at the exact bottom: 1-year forward return\n"
                     "(leverage amplifies V-shaped recoveries — but the low is only "
                     "obvious in hindsight)")
        ax.legend(title="Daily leverage")
        save_chart(fig, "F5_buy_leverage_at_lows.png")

    H["step5_event_studies"] = {
        r["event"] + f" ({r['horizon']})": {f"{L:g}x": r4(r[f"{L:g}x"]) for L in levs}
        for r in rows if r["horizon"] == "1yr"}


def table_to_headline(t: pd.DataFrame) -> dict:
    return {row["name"]: {"grew_1dollar_to": r4(row["grew_1dollar_to"]),
                          "cagr": r4(row["cagr"]), "volatility": r4(row["volatility"]),
                          "sharpe": r4(row["sharpe"]), "sortino": r4(row["sortino"]),
                          "calmar": r4(row["calmar"]), "max_drawdown": r4(row["max_drawdown"]),
                          "info_ratio_vs_sp": r4(row.get("info_ratio_vs_sp", float("nan")))}
            for _, row in t.iterrows()}


def _uptrend_strategies(daily_idx, u, rf_d):
    """Baselines + leverage-the-uptrend (above MA, 1x below), net of costs."""
    strat = {"Buy & Hold 1x": bt.buy_and_hold(u, rf_daily=rf_d, name="Buy & Hold 1x").net_returns,
             "MA200 -> Cash": bt.ma_to_cash(daily_idx, u, 200, rf_daily=rf_d).net_returns}
    for L in LEVS:
        strat[f"Lev {L:g}x above MA"] = bt.leveraged_above_ma(
            daily_idx, u, 200, L, rf_daily=rf_d, costs=config.DEFAULT_COSTS).net_returns
    return strat


# ===========================================================================
# Steps 6-8: every strategy family over full / 50y / 30y / 15y horizons
# ===========================================================================
def step6_above_horizons(daily_idx, u, rf_d):
    print("[step 6] leverage-the-uptrend over horizons ...")
    strat = _uptrend_strategies(daily_idx, u, rf_d)
    horizon_analysis(strat, "Leverage the uptrend (above MA, 1x below)",
                     "lev_above", rf_d, u.index.max())


def step7_cash_horizons(daily_idx, u, rf_d):
    print("[step 7] leverage->cash over horizons ...")
    strat = {"Buy & Hold 1x": bt.buy_and_hold(u, rf_daily=rf_d, name="Buy & Hold 1x").net_returns,
             "MA200 -> Cash": bt.ma_to_cash(daily_idx, u, 200, rf_daily=rf_d).net_returns}
    for L in LEVS:
        strat[f"Lev {L:g}x above->cash"] = bt.leverage_to_cash(
            daily_idx, u, 200, L, rf_daily=rf_d, costs=config.DEFAULT_COSTS).net_returns
    horizon_analysis(strat, "Leverage above the MA, cash below",
                     "lev_cash", rf_d, u.index.max())


def step8_three_tier_horizons(daily_idx, u, rf_d):
    print("[step 8] 3-tier (leverage/S&P/cash) over horizons ...")
    strat = {"Buy & Hold 1x": bt.buy_and_hold(u, rf_daily=rf_d, name="Buy & Hold 1x").net_returns,
             "MA200 -> Cash": bt.ma_to_cash(daily_idx, u, 200, rf_daily=rf_d).net_returns}
    for L in LEVS:
        strat[f"3-tier {L:g}x"] = bt.three_tier_strategy(
            daily_idx, u, L, 200, 63, rf_daily=rf_d, costs=config.DEFAULT_COSTS).net_returns
    horizon_analysis(strat, "3-tier: leverage / S&P / cash (3-month + 200-day MA)",
                     "lev_3tier", rf_d, u.index.max())


# ===========================================================================
# Step 9: does the MA switch add value over constant leverage?
# ===========================================================================
def step9_constant_vs_switch(daily_idx, u, rf_d):
    print("[step 9] constant leverage vs MA-switched leverage ...")
    bench = bt.buy_and_hold(u, rf_daily=rf_d, name="Buy & Hold 1x").net_returns
    strat = {"Buy & Hold 1x": bench}
    styles = {"Buy & Hold 1x": "-"}
    for L in LEVS:
        strat[f"Always {L:g}x (constant)"] = bt.always_leveraged(
            u, L, rf_daily=rf_d, costs=config.DEFAULT_COSTS).net_returns
        strat[f"Lev {L:g}x above MA"] = bt.leveraged_above_ma(
            daily_idx, u, 200, L, rf_daily=rf_d, costs=config.DEFAULT_COSTS).net_returns
        styles[f"Always {L:g}x (constant)"] = ":"     # constant = dotted
        styles[f"Lev {L:g}x above MA"] = "-"          # MA-switch = solid
    t = strat_table(strat, rf_d, bench=bench)
    save_table(t, "faber_step9_constant_vs_switch.csv")
    equity_chart(strat, "Constant leverage (dotted) vs MA-switched leverage (solid), net",
                 "F12_constant_vs_switch.png", styles=styles)
    H["step9_constant_vs_switch"] = table_to_headline(t)


# ===========================================================================
# Step 4: the inverted strategy (leverage ABOVE the MA)
# ===========================================================================
def step4_inverted(daily_idx, u, rf_d, bh, ma):
    print("[step 4] inverted strategy: leverage ABOVE the MA, 1x below ...")
    levs = LEVS
    rows = [metrics_row("Buy & Hold 1x", bh.net_returns, rf_d, 252,
                        {"strategy": "buy_hold"}),
            metrics_row("MA200 -> Cash", ma.net_returns, rf_d, 252,
                        {"strategy": "ma_to_cash"})]
    curves = {"Buy & Hold 1x": bh.equity, "MA200 -> Cash": ma.equity}
    ret_for_dd = {"Buy & Hold 1x": bh.net_returns, "MA200 -> Cash": ma.net_returns}
    # Keep net return series + tags so we can re-cut a 2000-onwards sub-period.
    net_ret = {"Buy & Hold 1x": bh.net_returns, "MA200 -> Cash": ma.net_returns}
    tags = {"Buy & Hold 1x": "buy_hold", "MA200 -> Cash": "ma_to_cash"}

    for L in levs:
        # Gross and NET (financing matters: leveraged ~70% of the time).
        gross = bt.leveraged_above_ma(daily_idx, u, 200, L, rf_daily=rf_d,
                                      costs=config.ZERO_COSTS)
        net = bt.leveraged_above_ma(daily_idx, u, 200, L, rf_daily=rf_d,
                                    costs=config.DEFAULT_COSTS)
        rows.append(metrics_row(f"Lev {L:g}x ABOVE (gross)", gross.net_returns, rf_d, 252,
                                {"strategy": "leveraged_above_ma_gross"}))
        rows.append(metrics_row(f"Lev {L:g}x ABOVE (net)", net.net_returns, rf_d, 252,
                                {"strategy": "leveraged_above_ma_net"}))
        curves[f"Lev {L:g}x ABOVE (net)"] = net.equity
        ret_for_dd[f"Lev {L:g}x ABOVE (net)"] = net.net_returns
        net_ret[f"Lev {L:g}x ABOVE (net)"] = net.net_returns
        tags[f"Lev {L:g}x ABOVE (net)"] = "leveraged_above_ma_net"

    # The "buy leverage LOW" direction (leverage BELOW the MA) at each level, net.
    for L in levs:
        below = bt.leveraged_bad_market(daily_idx, u, 200, L, rf_daily=rf_d,
                                        costs=config.DEFAULT_COSTS)
        nm = f"Lev {L:g}x BELOW (net)"
        rows.append(metrics_row(nm, below.net_returns, rf_d, 252,
                                {"strategy": "leveraged_below_ma_net"}))
        net_ret[nm] = below.net_returns
        tags[nm] = "leveraged_below_ma_net"

    tbl = pd.DataFrame(rows)
    save_table(tbl, "faber_step4_inverted_strategy.csv")

    # Closer picture: the SAME strategies, but only from 2000 onwards.
    rows2000 = [period_metrics(name, r, rf_d, "2000-01-01", tags[name])
                for name, r in net_ret.items()]
    tbl2000 = pd.DataFrame(rows2000)
    save_table(tbl2000, "faber_step4_inverted_2000plus.csv")

    fig = pl.plot_equity_comparison(
        curves, "Step 4 — Leverage ABOVE the MA (net of costs) vs baselines",
        "F4_inverted_equity.png")
    save_chart(fig, "F4_inverted_equity.png")
    fig = pl.plot_drawdowns(
        ret_for_dd, "Step 4 — Drawdowns: leverage ABOVE the MA vs baselines",
        "F4_inverted_drawdowns.png")
    save_chart(fig, "F4_inverted_drawdowns.png")

    # Direction comparison at 2x: leverage ABOVE vs BELOW the MA (+ baselines).
    dirc = {n: rt.cumulative_index(net_ret[n]) for n in
            ("Buy & Hold 1x", "MA200 -> Cash", "Lev 2x ABOVE (net)", "Lev 2x BELOW (net)")}
    fig = pl.plot_equity_comparison(
        dirc, "Which direction? Leverage ABOVE vs BELOW the 200-day MA (2x, net)",
        "F4_direction_comparison.png",
        colors={"Buy & Hold 1x": config.COLORS["buy_hold"],
                "MA200 -> Cash": config.COLORS["ma_cash"],
                "Lev 2x ABOVE (net)": config.COLORS["leveraged"],
                "Lev 2x BELOW (net)": config.COLORS["neutral"]})
    save_chart(fig, "F4_direction_comparison.png")

    # "Buy leverage LOW" (below the MA) equity + drawdowns, for the switching step.
    below_curves = {"Buy & Hold 1x": bh.equity, "MA200 -> Cash": ma.equity}
    below_dd = {"Buy & Hold 1x": bh.net_returns, "MA200 -> Cash": ma.net_returns}
    for L in levs:
        below_curves[f"Lev {L:g}x BELOW (net)"] = rt.cumulative_index(net_ret[f"Lev {L:g}x BELOW (net)"])
        below_dd[f"Lev {L:g}x BELOW (net)"] = net_ret[f"Lev {L:g}x BELOW (net)"]
    fig = pl.plot_equity_comparison(
        below_curves, "Buy leverage LOW (below the 200-day MA) vs baselines",
        "F6_below_equity.png")
    save_chart(fig, "F6_below_equity.png")
    fig = pl.plot_drawdowns(
        below_dd, "Drawdowns: buy leverage LOW (below the 200-day MA)",
        "F6_below_drawdowns.png")
    save_chart(fig, "F6_below_drawdowns.png")

    # Headline: best inverted (net) by Sharpe vs buy&hold.
    inv = tbl[tbl["strategy"] == "leveraged_above_ma_net"].copy()
    best = inv.loc[inv["sharpe"].idxmax()]
    bh_row = tbl[tbl["strategy"] == "buy_hold"].iloc[0]
    H["step4_inverted"] = {
        "buy_hold": {k: r4(bh_row[k]) for k in ("cagr", "sharpe", "max_drawdown", "calmar")},
        "best_inverted_net": {"name": best["name"], "cagr": r4(best["cagr"]),
                              "sharpe": r4(best["sharpe"]),
                              "max_drawdown": r4(best["max_drawdown"]),
                              "calmar": r4(best["calmar"])},
        "inverted_net_by_leverage": {
            row["name"]: {"cagr": r4(row["cagr"]), "sharpe": r4(row["sharpe"]),
                          "max_drawdown": r4(row["max_drawdown"]), "calmar": r4(row["calmar"])}
            for _, row in inv.iterrows()},
        "below_net_by_leverage": {
            row["name"]: {"cagr": r4(row["cagr"]), "sharpe": r4(row["sharpe"]),
                          "max_drawdown": r4(row["max_drawdown"]), "calmar": r4(row["calmar"])}
            for _, row in tbl[tbl["strategy"] == "leveraged_below_ma_net"].iterrows()},
    }
    H["step4_inverted_2000plus"] = {
        row["name"]: {"cagr": r4(row["cagr"]), "sharpe": r4(row["sharpe"]),
                      "max_drawdown": r4(row["max_drawdown"]), "calmar": r4(row["calmar"])}
        for _, row in tbl2000.iterrows()}


# ===========================================================================
def main():
    print("=" * 70)
    print(" Faber replication + leverage study (v2)")
    print("=" * 70)

    # --- data ---
    print("[data] building long-history total return ...")
    daily_idx, meta = lh.long_daily_tr()
    monthly_idx = lh.combined_monthly_tr(start="1901-01-01")
    u = rt.simple_returns(daily_idx)
    rf_d = lh.long_risk_free_daily(u.index)
    rf_m = lh.long_risk_free_monthly(rt.simple_returns(monthly_idx).index)
    vcheck = lh.validate_reconstruction()
    print(f"    daily TR {meta['start']}..{meta['end']} (splice {meta.get('splice_date')}); "
          f"recon TE={vcheck.get('tracking_error_ann', float('nan')):.4f}")
    H["data"] = {"daily": meta, "reconstruction_check": {k: r4(v) for k, v in vcheck.items()},
                 "monthly_start": str(monthly_idx.index.min().date()),
                 "monthly_end": str(monthly_idx.index.max().date()),
                 "risk_free": "Yahoo ^IRX (1960+) + 3.5% constant proxy before 1960"}

    bh_m, tim_m = step0_faber(monthly_idx, rf_m)
    bh, ma, u = step1_baseline(daily_idx, rf_d)
    step2_leverage_index(daily_idx, u, rf_d, bh, ma)
    step3_surfaces(u, rf_d)
    step3b_breakeven_chart(u, rf_d)
    step3c_zero_return_map(u)
    step5_event_studies(daily_idx, u)
    step4_inverted(daily_idx, u, rf_d, bh, ma)
    step6_above_horizons(daily_idx, u, rf_d)
    step7_cash_horizons(daily_idx, u, rf_d)
    step8_three_tier_horizons(daily_idx, u, rf_d)
    step9_constant_vs_switch(daily_idx, u, rf_d)

    with open(config.RESULTS_DIR / "headline_faber.json", "w") as f:
        json.dump(H, f, indent=2, default=str)
    print("\n[done] headline -> results/headline_faber.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
