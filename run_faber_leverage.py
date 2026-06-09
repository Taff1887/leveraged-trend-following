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
    return bh, ma, u


# ===========================================================================
# Step 2: daily leverage on the index
# ===========================================================================
def step2_leverage_index(daily_idx, u, rf_d, bh, ma):
    print("[step 2] daily leverage on the index (1.5x / 2.5x / 3x) ...")
    levs = [1.5, 2.5, 3.0]
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
# Step 4: the inverted strategy (leverage ABOVE the MA)
# ===========================================================================
def step4_inverted(daily_idx, u, rf_d, bh, ma):
    print("[step 4] inverted strategy: leverage ABOVE the MA, 1x below ...")
    levs = [1.5, 2.0, 3.0]
    rows = [metrics_row("Buy & Hold 1x", bh.net_returns, rf_d, 252,
                        {"strategy": "buy_hold"}),
            metrics_row("MA200 -> Cash", ma.net_returns, rf_d, 252,
                        {"strategy": "ma_to_cash"})]
    curves = {"Buy & Hold 1x": bh.equity, "MA200 -> Cash": ma.equity}
    ret_for_dd = {"Buy & Hold 1x": bh.net_returns, "MA200 -> Cash": ma.net_returns}

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

    # For contrast: the ORIGINAL idea (leverage BELOW the MA) at 2x, net.
    below2 = bt.leveraged_bad_market(daily_idx, u, 200, 2.0, rf_daily=rf_d,
                                     costs=config.DEFAULT_COSTS)
    rows.append(metrics_row("Lev 2x BELOW (net) [original]", below2.net_returns, rf_d, 252,
                            {"strategy": "leveraged_below_ma_net"}))

    tbl = pd.DataFrame(rows)
    save_table(tbl, "faber_step4_inverted_strategy.csv")

    fig = pl.plot_equity_comparison(
        curves, "Step 4 — Leverage ABOVE the MA (net of costs) vs baselines",
        "F4_inverted_equity.png")
    save_chart(fig, "F4_inverted_equity.png")
    fig = pl.plot_drawdowns(
        ret_for_dd, "Step 4 — Drawdowns: leverage ABOVE the MA vs baselines",
        "F4_inverted_drawdowns.png")
    save_chart(fig, "F4_inverted_drawdowns.png")

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
        "original_below_2x_net": {
            k: r4(tbl[tbl.strategy == "leveraged_below_ma_net"].iloc[0][k])
            for k in ("cagr", "sharpe", "max_drawdown", "calmar")},
    }


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
    step4_inverted(daily_idx, u, rf_d, bh, ma)

    with open(config.RESULTS_DIR / "headline_faber.json", "w") as f:
        json.dump(H, f, indent=2, default=str)
    print("\n[done] headline -> results/headline_faber.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
