"""
sweep.py
========

Part 4 (parameter sweep) and Part 5 (period / episode analysis).

The parameter sweep runs every combination of {moving-average window} x
{leverage level} x {cost assumption} and records the headline metrics in one
tidy table. The period analysis slices a set of strategies into market regimes
(1990 onward, post-GFC, COVID crash, ...) and asks "did leverage help here?".

We keep this honest: the sweep is run on the SAME data and uses the SAME
look-ahead-safe signals as everything else, and we always carry buy-and-hold and
MA-to-cash alongside so the leveraged variant is judged against real baselines,
not against nothing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .backtest import (buy_and_hold, ma_to_cash, leveraged_bad_market)
from .metrics import summarize, cagr, annual_volatility, sharpe_ratio, \
    sortino_ratio, max_drawdown, calmar_ratio, drawdown_table


# ---------------------------------------------------------------------------
# Part 4: parameter sweep
# ---------------------------------------------------------------------------
def run_parameter_sweep(prices: pd.Series, underlying_returns: pd.Series,
                        rf_daily=0.0, ma_windows: list[int] | None = None,
                        leverages: list[float] | None = None,
                        cost_scenarios: dict | None = None) -> pd.DataFrame:
    """Run the full leverage x window x cost sweep and return a tidy results table.

    ``cost_scenarios`` maps a label -> cost dict, e.g.
        {"gross (0 cost)": ZERO_COSTS, "net (realistic)": DEFAULT_COSTS}.
    """
    ma_windows = ma_windows or config.MA_WINDOWS
    leverages = leverages or config.LEVERAGE_LEVELS
    if cost_scenarios is None:
        cost_scenarios = {
            "gross (0 cost)": config.ZERO_COSTS,
            "net (realistic)": config.DEFAULT_COSTS,
        }

    rows = []
    for cost_label, costs in cost_scenarios.items():
        # Baselines for this cost scenario.
        bh = buy_and_hold(underlying_returns, rf_daily=rf_daily, costs=costs)
        rows.append(_sweep_row(bh, rf_daily, window=np.nan, leverage=1.0,
                               strategy="buy_and_hold", cost_label=cost_label))

        for w in ma_windows:
            mac = ma_to_cash(prices, underlying_returns, w, rf_daily=rf_daily,
                             costs=costs)
            rows.append(_sweep_row(mac, rf_daily, window=w, leverage=0.0,
                                   strategy="ma_to_cash", cost_label=cost_label))

            for L in leverages:
                lev = leveraged_bad_market(prices, underlying_returns, w, L,
                                           rf_daily=rf_daily, costs=costs)
                rows.append(_sweep_row(lev, rf_daily, window=w, leverage=L,
                                       strategy="leveraged_bad_market",
                                       cost_label=cost_label))

    df = pd.DataFrame(rows)
    return df


def _sweep_row(result, rf_daily, window, leverage, strategy, cost_label) -> dict:
    """Make one tidy row from a StrategyResult."""
    s = result.summary(rf_daily=rf_daily)
    return {
        "strategy": strategy,
        "cost_scenario": cost_label,
        "window": window,
        "leverage": leverage,
        "name": result.name,
        "cagr": s["cagr"],
        "volatility": s["volatility"],
        "sharpe": s["sharpe"],
        "sortino": s["sortino"],
        "max_drawdown": s["max_drawdown"],
        "calmar": s["calmar"],
        "total_return": s["total_return"],
        "n_switches": s.get("n_switches", np.nan),
        "years": s["years"],
    }


def beats_baseline(sweep_df: pd.DataFrame, cost_label: str) -> pd.DataFrame:
    """Flag leveraged strategies that beat buy-and-hold on each metric.

    Returns the leveraged rows for ``cost_label`` with boolean 'beats_*' columns.
    'Beats' means strictly better: higher CAGR/Sharpe/Calmar, or a shallower
    (less negative) max drawdown.
    """
    sub = sweep_df[sweep_df["cost_scenario"] == cost_label]
    bh = sub[sub["strategy"] == "buy_and_hold"].iloc[0]
    # Only count GENUINE leverage (>1x). Leverage = 1.0 is the degenerate case
    # that simply reproduces buy-and-hold, so it would not be a fair "winner".
    lev = sub[(sub["strategy"] == "leveraged_bad_market")
              & (sub["leverage"] > 1.0)].copy()
    lev["beats_cagr"] = lev["cagr"] > bh["cagr"]
    lev["beats_sharpe"] = lev["sharpe"] > bh["sharpe"]
    lev["beats_calmar"] = lev["calmar"] > bh["calmar"]
    lev["beats_maxdd"] = lev["max_drawdown"] > bh["max_drawdown"]  # less negative
    lev["beats_all"] = (lev["beats_cagr"] & lev["beats_sharpe"]
                        & lev["beats_calmar"] & lev["beats_maxdd"])
    return lev


def heatmap_matrix(sweep_df: pd.DataFrame, value: str, cost_label: str) -> pd.DataFrame:
    """Pivot the leveraged-strategy sweep into a (window x leverage) matrix."""
    sub = sweep_df[(sweep_df["cost_scenario"] == cost_label)
                   & (sweep_df["strategy"] == "leveraged_bad_market")]
    mat = sub.pivot(index="window", columns="leverage", values=value)
    return mat


# ---------------------------------------------------------------------------
# Part 5: period & episode analysis
# ---------------------------------------------------------------------------
def _slice_metrics(returns: pd.Series, start, end, rf_daily=0.0) -> dict:
    """Metrics for a return stream restricted to [start, end].

    ``rf_daily`` (scalar or Series) is the risk-free rate used for the Sharpe and
    Sortino ratios, so they are consistent with the rest of the project.
    """
    r = returns.copy()
    if start is not None:
        r = r[r.index >= pd.Timestamp(start)]
    if end is not None:
        r = r[r.index <= pd.Timestamp(end)]
    r = r.dropna()
    if len(r) < 5:
        return None
    rf = rf_daily.reindex(r.index).fillna(0.0) if isinstance(rf_daily, pd.Series) else rf_daily
    dd = drawdown_table(r, top_n=1)
    rec_days = dd["recovery_days"].iloc[0] if len(dd) else np.nan
    return {
        "n_days": len(r),
        "total_return": (1 + r).prod() - 1,
        "cagr": cagr(r),
        "volatility": annual_volatility(r),
        "sharpe": sharpe_ratio(r, rf),
        "max_drawdown": max_drawdown(r),
        "calmar": calmar_ratio(r),
        "deepest_dd_recovery_days": rec_days,
    }


def evaluate_periods(strategies: dict, periods: list[tuple], rf_daily=0.0) -> pd.DataFrame:
    """Evaluate several strategies across several (label, start, end) periods.

    ``strategies`` maps a display name -> a daily net-return Series.
    ``rf_daily`` is the risk-free rate for Sharpe (scalar or aligned Series).
    Returns a long/tidy table with one row per (period, strategy).
    """
    rows = []
    for label, start, end in periods:
        for name, returns in strategies.items():
            m = _slice_metrics(returns, start, end, rf_daily=rf_daily)
            if m is None:
                continue
            row = {"period": label, "strategy": name}
            row.update(m)
            rows.append(row)
    return pd.DataFrame(rows)


def did_leverage_help(period_table: pd.DataFrame, bh_name: str,
                      lev_name: str, metric: str = "total_return") -> pd.DataFrame:
    """For each period, compare a leveraged strategy to buy-and-hold on ``metric``.

    Returns a compact table with the two values and a 'leverage_helped' flag.
    """
    rows = []
    for period in period_table["period"].unique():
        sub = period_table[period_table["period"] == period]
        bh = sub[sub["strategy"] == bh_name]
        lev = sub[sub["strategy"] == lev_name]
        if bh.empty or lev.empty:
            continue
        bh_v = bh[metric].iloc[0]
        lev_v = lev[metric].iloc[0]
        # For drawdown, "better" means less negative; for everything else, higher.
        if metric == "max_drawdown":
            helped = lev_v > bh_v
        else:
            helped = lev_v > bh_v
        rows.append({
            "period": period,
            f"{bh_name}_{metric}": bh_v,
            f"{lev_name}_{metric}": lev_v,
            "difference": lev_v - bh_v,
            "leverage_helped": helped,
        })
    return pd.DataFrame(rows)
