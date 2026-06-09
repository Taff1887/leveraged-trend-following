"""
monte_carlo.py
==============

A Monte Carlo laboratory for the central question behind leverage:

    "For an asset with a given DRIFT and VOLATILITY, what does daily-rebalanced
     leverage do to long-run wealth -- and when does volatility decay destroy it?"

We simulate many random daily-return paths for a 1x asset, then apply each
leverage multiple to the SAME paths (this is the 'common random numbers' trick,
which makes 'probability 2x beats 1x' a fair, apples-to-apples comparison).

Everything is plain NumPy and fully reproducible from a seed.

The mechanics in one line
-------------------------
    leveraged daily return = leverage * (1x daily return)        (rebalanced daily)
    terminal wealth        = product over days of (1 + leveraged daily return)

Because we COMPOUND the leveraged daily returns, volatility decay is built in:
a leveraged asset's growth rate is roughly  L*mu - 0.5 * L^2 * sigma^2, so the
``-0.5 * L^2 * sigma^2`` term (the "variance drag") grows with the SQUARE of
leverage. That single term is the whole story of why high leverage can lose money
even when the underlying drifts upward.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

TD = config.TRADING_DAYS_PER_YEAR


# ---------------------------------------------------------------------------
# Path simulation
# ---------------------------------------------------------------------------
def simulate_base_returns(drift_annual: float, vol_annual: float, n_days: int,
                          n_paths: int, rng: np.random.Generator,
                          serial_corr: float = 0.0,
                          fat_tails: bool = False, t_df: float = 5.0) -> np.ndarray:
    """Simulate daily simple returns for a 1x asset. Shape ``(n_paths, n_days)``.

    Parameters
    ----------
    drift_annual : expected annual *arithmetic* return (e.g. 0.08 for 8%).
    vol_annual   : annual volatility (e.g. 0.20 for 20%).
    serial_corr  : optional AR(1) coefficient on the daily shocks (0 = i.i.d.).
    fat_tails    : if True, use a Student-t shock (heavier crashes) instead of
                   a normal shock.
    """
    mu_d = drift_annual / TD
    sig_d = vol_annual / np.sqrt(TD)

    if fat_tails:
        # Student-t scaled to unit variance, so vol_annual still means what it says.
        z = rng.standard_t(t_df, size=(n_paths, n_days))
        z = z / np.sqrt(t_df / (t_df - 2.0))
    else:
        z = rng.standard_normal(size=(n_paths, n_days))

    if serial_corr != 0.0:
        # Apply AR(1) to the standardized shocks along the time axis.
        out = np.empty_like(z)
        out[:, 0] = z[:, 0]
        scale = np.sqrt(1.0 - serial_corr ** 2)
        for t in range(1, n_days):
            out[:, t] = serial_corr * out[:, t - 1] + scale * z[:, t]
        z = out

    return mu_d + sig_d * z


def path_stats(daily_returns: np.ndarray, years: float) -> dict:
    """Vectorised per-path statistics for a matrix of daily returns.

    Returns arrays (one value per path) for terminal wealth, CAGR, vol, Sharpe,
    and max drawdown. A leveraged daily move below -100% is floored at total
    wipeout (wealth -> 0), matching the reality that you cannot lose more than
    your capital in a day.
    """
    growth = np.maximum(1.0 + daily_returns, 0.0)          # floor at wipeout
    equity = np.cumprod(growth, axis=1)
    terminal = equity[:, -1]

    peak = np.maximum.accumulate(equity, axis=1)
    drawdown = equity / peak - 1.0
    max_dd = drawdown.min(axis=1)

    # Compute Sharpe/vol from the SAME floored daily returns used for the equity
    # path (a day that wipes out the account is a -100% effective return, not the
    # raw <-100% number), so the risk stats stay consistent with terminal wealth.
    effective = growth - 1.0
    mean_d = effective.mean(axis=1)
    std_d = effective.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        sharpe = np.where(std_d > 0, mean_d / std_d * np.sqrt(TD), np.nan)
        cagr = np.where(terminal > 0, terminal ** (1.0 / years) - 1.0, -1.0)
    vol = std_d * np.sqrt(TD)

    return {"terminal": terminal, "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "max_dd": max_dd}


# ---------------------------------------------------------------------------
# One cell of the grid: a (drift, vol) point across all leverages & horizons
# ---------------------------------------------------------------------------
def simulate_cell(drift_annual: float, vol_annual: float, leverages: list[float],
                  horizons_years: list[int], n_paths: int, seed: int,
                  serial_corr: float = 0.0, fat_tails: bool = False) -> list[dict]:
    """Simulate one (drift, vol) point and summarise every leverage x horizon.

    We simulate the LONGEST horizon once and reuse its prefixes for shorter
    horizons (nested paths), and we apply every leverage to the SAME base paths
    so 'probability of beating 1x' is computed on identical draws.
    """
    rng = np.random.default_rng(seed)
    max_years = max(horizons_years)
    max_days = int(max_years * TD)
    base = simulate_base_returns(drift_annual, vol_annual, max_days, n_paths, rng,
                                 serial_corr=serial_corr, fat_tails=fat_tails)

    rows = []
    for years in horizons_years:
        days = int(years * TD)
        base_h = base[:, :days]
        # 1x terminal wealth on these same paths (the benchmark to beat).
        one_x_terminal = path_stats(base_h, years)["terminal"]
        for L in leverages:
            stats = path_stats(L * base_h, years)
            term = stats["terminal"]
            rows.append({
                "drift": drift_annual,
                "vol": vol_annual,
                "leverage": L,
                "horizon_years": years,
                "median_terminal": float(np.median(term)),
                "mean_terminal": float(np.mean(term)),
                "median_cagr": float(np.median(stats["cagr"])),
                "mean_cagr": float(np.mean(stats["cagr"])),
                "median_vol": float(np.median(stats["vol"])),
                "median_sharpe": float(np.nanmedian(stats["sharpe"])),
                "median_max_dd": float(np.median(stats["max_dd"])),
                "worst_max_dd": float(np.min(stats["max_dd"])),
                "prob_loss": float(np.mean(term < 1.0)),
                "prob_beat_1x": float(np.mean(term > one_x_terminal)),
                "prob_dd_gt_50": float(np.mean(stats["max_dd"] <= -0.50)),
                "prob_dd_gt_70": float(np.mean(stats["max_dd"] <= -0.70)),
                "prob_dd_gt_90": float(np.mean(stats["max_dd"] <= -0.90)),
            })
    return rows


# ---------------------------------------------------------------------------
# The full grid
# ---------------------------------------------------------------------------
def run_grid(drifts: list[float] | None = None, vols: list[float] | None = None,
             leverages: list[float] | None = None,
             horizons_years: list[int] | None = None,
             n_paths: int | None = None, base_seed: int | None = None,
             serial_corr: float = 0.0, fat_tails: bool = False,
             verbose: bool = True) -> pd.DataFrame:
    """Run the full drift x vol x leverage x horizon grid; return a tidy DataFrame.

    Each (drift, vol) point gets its own deterministic seed so the whole grid is
    reproducible and parallel-safe.
    """
    drifts = drifts or config.MC_ANNUAL_DRIFTS
    vols = vols or config.MC_ANNUAL_VOLS
    leverages = leverages or config.MC_LEVERAGES
    horizons_years = horizons_years or config.MC_HORIZONS_YEARS
    n_paths = n_paths or config.MC_N_PATHS
    base_seed = config.RANDOM_SEED if base_seed is None else base_seed

    all_rows = []
    total = len(drifts) * len(vols)
    k = 0
    for di, d in enumerate(drifts):
        for vi, v in enumerate(vols):
            k += 1
            # Unique, reproducible seed per (drift, vol) cell.
            seed = base_seed + di * 1000 + vi
            if verbose:
                print(f"  MC cell {k}/{total}: drift={d:.0%}, vol={v:.0%}")
            all_rows.extend(
                simulate_cell(d, v, leverages, horizons_years, n_paths, seed,
                              serial_corr=serial_corr, fat_tails=fat_tails)
            )
    return pd.DataFrame(all_rows)


# ---------------------------------------------------------------------------
# Post-processing helpers for heatmaps
# ---------------------------------------------------------------------------
def optimal_leverage_grid(grid: pd.DataFrame, horizon_years: int,
                          objective: str = "median_terminal") -> pd.DataFrame:
    """For each (drift, vol), the leverage that maximises ``objective``.

    Returns a matrix with vol as rows and drift as columns (ready for a heatmap).
    """
    sub = grid[grid["horizon_years"] == horizon_years]
    idx = sub.groupby(["drift", "vol"])[objective].idxmax()
    best = sub.loc[idx]
    return best.pivot(index="vol", columns="drift", values="leverage")


def metric_grid(grid: pd.DataFrame, horizon_years: int, leverage: float,
                metric: str) -> pd.DataFrame:
    """Matrix of ``metric`` (vol x drift) for a fixed leverage and horizon."""
    sub = grid[(grid["horizon_years"] == horizon_years)
               & (grid["leverage"] == leverage)]
    return sub.pivot(index="vol", columns="drift", values=metric)


def prob_beat_1x_grid(grid: pd.DataFrame, horizon_years: int,
                      leverage: float) -> pd.DataFrame:
    """Matrix of P(leverage beats 1x) (vol x drift) for a fixed leverage/horizon."""
    return metric_grid(grid, horizon_years, leverage, "prob_beat_1x")


# ---------------------------------------------------------------------------
# Teaching example: the arithmetic of volatility decay
# ---------------------------------------------------------------------------
def vol_decay_table() -> pd.DataFrame:
    """The textbook +10% / -10% example for 1x, 2x, 3x.

    Shows that a round trip of +10% then -10% LOSES money, and the loss grows
    with the square of leverage.
    """
    rows = []
    for L in [1.0, 2.0, 3.0]:
        up = 1.0 + L * 0.10
        down = 1.0 + L * (-0.10)
        two_day = up * down - 1.0
        rows.append({
            "leverage": f"{L:g}x",
            "day1_+10%_move": L * 0.10,
            "day2_-10%_move": L * -0.10,
            "after_day1": up,
            "after_day2": up * down,
            "two_day_return": two_day,
        })
    return pd.DataFrame(rows)


def variance_drag(leverage: float, vol_annual: float) -> float:
    """The approximate annual growth penalty from variance drag: 0.5 * L^2 * sigma^2.

    This closed-form term explains the Monte Carlo results: doubling leverage
    QUADRUPLES the drag.
    """
    return 0.5 * (leverage ** 2) * (vol_annual ** 2)
