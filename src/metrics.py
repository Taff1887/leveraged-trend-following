"""
metrics.py
==========

Performance and risk statistics. Each function takes a daily simple-return
series (or an equity curve) and returns a single number, so they are easy to
test and easy to read. The big convenience function is :func:`summarize`, which
bundles everything the project reports into one dict.

Everything is computed from DAILY simple returns with daily compounding, which
is consistent with how the backtest and Monte Carlo engines build wealth.

A quick glossary (all defined precisely in the research paper):
* CAGR        : the constant annual growth rate that turns the start wealth into
                the end wealth over the actual number of years.
* Volatility  : annualized standard deviation of daily returns.
* Sharpe      : excess return per unit of total volatility.
* Sortino     : like Sharpe but only penalizes *downside* volatility.
* Max drawdown: the worst peak-to-trough loss of the equity curve.
* Calmar      : CAGR divided by the absolute max drawdown (return per unit of pain).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TRADING_DAYS_PER_YEAR
from .returns import cumulative_index, to_monthly_returns


# ---------------------------------------------------------------------------
# Basic building blocks
# ---------------------------------------------------------------------------
def n_years(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Length of the sample in calendar years.

    ``periods_per_year`` is 252 for daily data (the default) or 12 for monthly,
    so the same metrics work for the daily backtest and the monthly Faber rule.
    """
    return len(returns) / periods_per_year


def cagr(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Compound annual growth rate from a simple-return series."""
    returns = returns.dropna()
    if len(returns) == 0:
        return np.nan
    total_growth = (1.0 + returns).prod()
    yrs = n_years(returns, periods_per_year)
    if yrs <= 0 or total_growth <= 0:
        return np.nan
    return total_growth ** (1.0 / yrs) - 1.0


def annual_volatility(returns: pd.Series,
                      periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized standard deviation of returns."""
    returns = returns.dropna()
    if len(returns) < 2:
        return np.nan
    return returns.std(ddof=1) * np.sqrt(periods_per_year)


def sharpe_ratio(returns: pd.Series, rf_daily: pd.Series | float = 0.0,
                 periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized Sharpe ratio.

    rf_daily can be a constant per-period risk-free rate or a Series aligned to
    ``returns``. We subtract it to get *excess* returns, then annualize mean/std
    using ``periods_per_year``.
    """
    returns = returns.dropna()
    if len(returns) < 2:
        return np.nan
    if isinstance(rf_daily, pd.Series):
        excess = returns - rf_daily.reindex(returns.index).fillna(0.0)
    else:
        excess = returns - rf_daily
    sd = excess.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return np.nan
    return (excess.mean() / sd) * np.sqrt(periods_per_year)


def sortino_ratio(returns: pd.Series, rf_daily: pd.Series | float = 0.0,
                  target: float = 0.0,
                  periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized Sortino ratio: excess return divided by *downside* deviation.

    Downside deviation only counts periods where the (excess) return fell below
    the ``target`` (default 0). This rewards strategies whose volatility is mostly
    to the upside.
    """
    returns = returns.dropna()
    if len(returns) < 2:
        return np.nan
    if isinstance(rf_daily, pd.Series):
        excess = returns - rf_daily.reindex(returns.index).fillna(0.0)
    else:
        excess = returns - rf_daily
    # Standard target downside deviation: square the shortfalls below the target
    # (up days count as zero shortfall) and average over ALL observations, not
    # just the down days. Averaging over down days only would inflate the
    # deviation by sqrt(n_total / n_down) and could distort cross-strategy
    # rankings, since strategies differ in how often they have down days.
    shortfall = np.minimum(excess - target, 0.0)
    downside_dev = np.sqrt((shortfall ** 2).mean())
    if downside_dev == 0 or np.isnan(downside_dev):
        return np.nan
    return ((excess.mean() - target) / downside_dev) * np.sqrt(periods_per_year)


def information_ratio(returns: pd.Series, benchmark: pd.Series,
                      periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Annualized information ratio: active return over a benchmark divided by the
    tracking error (the std of the active return).

        active_t = returns_t - benchmark_t
        IR = annualized mean(active) / annualized std(active)

    Here the benchmark is the S&P 500 (buy & hold). For the benchmark itself the
    active return is identically zero, so IR is undefined (returns NaN).
    """
    df = pd.concat([returns, benchmark], axis=1, join="inner").dropna()
    if len(df) < 2:
        return np.nan
    active = df.iloc[:, 0] - df.iloc[:, 1]
    sd = active.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return np.nan
    return (active.mean() / sd) * np.sqrt(periods_per_year)


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Drawdown at each date: current wealth divided by the running peak, minus 1.

    A value of -0.30 means the equity curve is 30% below its highest prior point.
    """
    equity = cumulative_index(returns)
    running_peak = equity.cummax()
    return equity / running_peak - 1.0


def max_drawdown(returns: pd.Series) -> float:
    """The single worst drawdown (a negative number, e.g. -0.55 = -55%)."""
    dd = drawdown_series(returns)
    if len(dd) == 0:
        return np.nan
    return dd.min()


def calmar_ratio(returns: pd.Series,
                 periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """CAGR divided by the absolute value of max drawdown."""
    mdd = max_drawdown(returns)
    if mdd is None or np.isnan(mdd) or mdd == 0:
        return np.nan
    return cagr(returns, periods_per_year) / abs(mdd)


def drawdown_table(returns: pd.Series, top_n: int = 5) -> pd.DataFrame:
    """The ``top_n`` deepest drawdown episodes with start, trough, recovery dates.

    Recovery date is the first day the equity curve regains its prior peak; if it
    never recovers within the sample, recovery is NaT and the episode is ongoing.
    """
    equity = cumulative_index(returns)
    peak = equity.cummax()
    dd = equity / peak - 1.0

    episodes = []
    in_dd = False
    start = trough = None
    trough_val = 0.0
    for date, value in dd.items():
        if not in_dd and value < 0:
            in_dd = True
            start = date
            trough = date
            trough_val = value
        elif in_dd:
            if value < trough_val:
                trough_val = value
                trough = date
            if value >= 0:  # fully recovered
                episodes.append((start, trough, date, trough_val))
                in_dd = False
    if in_dd:  # an unfinished drawdown at the end of the sample
        episodes.append((start, trough, pd.NaT, trough_val))

    if not episodes:
        return pd.DataFrame(
            columns=["start", "trough", "recovery", "depth", "recovery_days"]
        )

    rows = []
    for start, trough, recovery, depth in episodes:
        if pd.isna(recovery):
            rec_days = np.nan
        else:
            rec_days = (recovery - start).days
        rows.append(
            {
                "start": start,
                "trough": trough,
                "recovery": recovery,
                "depth": depth,
                "recovery_days": rec_days,
            }
        )
    out = pd.DataFrame(rows).sort_values("depth").head(top_n).reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# Distribution / day-level statistics
# ---------------------------------------------------------------------------
def best_worst(returns: pd.Series) -> dict:
    """Best/worst single day and month, plus the % of positive days and months."""
    returns = returns.dropna()
    monthly = to_monthly_returns(returns)
    return {
        "worst_day": returns.min(),
        "best_day": returns.max(),
        "worst_month": monthly.min() if len(monthly) else np.nan,
        "best_month": monthly.max() if len(monthly) else np.nan,
        "pct_positive_days": (returns > 0).mean(),
        "pct_positive_months": (monthly > 0).mean() if len(monthly) else np.nan,
    }


# ---------------------------------------------------------------------------
# Rolling statistics (for charts in Part 2)
# ---------------------------------------------------------------------------
def rolling_cagr(returns: pd.Series, years: int = 3) -> pd.Series:
    """Rolling annualized return over a window of ``years`` (default 3 years)."""
    window = int(years * TRADING_DAYS_PER_YEAR)
    growth = (1.0 + returns.fillna(0.0)).rolling(window).apply(np.prod, raw=True)
    return growth ** (1.0 / years) - 1.0


def rolling_sharpe(returns: pd.Series, years: int = 3,
                   rf_daily: float = 0.0) -> pd.Series:
    """Rolling annualized Sharpe ratio over a window of ``years``."""
    window = int(years * TRADING_DAYS_PER_YEAR)
    excess = returns.fillna(0.0) - rf_daily
    mean = excess.rolling(window).mean()
    std = excess.rolling(window).std(ddof=1)
    return (mean / std) * np.sqrt(TRADING_DAYS_PER_YEAR)


# ---------------------------------------------------------------------------
# The one-stop summary
# ---------------------------------------------------------------------------
def summarize(returns: pd.Series, rf_daily: pd.Series | float = 0.0,
              name: str | None = None,
              periods_per_year: int = TRADING_DAYS_PER_YEAR) -> dict:
    """Return a dictionary of every headline metric for a return stream.

    This is what the backtest, parameter sweep, and notebooks call to describe a
    strategy in one row. Pass ``periods_per_year=12`` for monthly series.
    """
    returns = returns.dropna()
    pp = periods_per_year
    stats = {
        "name": name,
        "start": returns.index.min() if len(returns) else pd.NaT,
        "end": returns.index.max() if len(returns) else pd.NaT,
        "n_days": len(returns),
        "years": n_years(returns, pp),
        "total_return": (1.0 + returns).prod() - 1.0 if len(returns) else np.nan,
        "cagr": cagr(returns, pp),
        "volatility": annual_volatility(returns, pp),
        "sharpe": sharpe_ratio(returns, rf_daily, pp),
        "sortino": sortino_ratio(returns, rf_daily, periods_per_year=pp),
        "max_drawdown": max_drawdown(returns),
        "calmar": calmar_ratio(returns, pp),
    }
    if pp == TRADING_DAYS_PER_YEAR:
        stats.update(best_worst(returns))  # day/month stats only meaningful daily
    if name is None:
        stats.pop("name")
    return stats


def summary_frame(summaries: list[dict]) -> pd.DataFrame:
    """Stack several :func:`summarize` dicts into a tidy, ordered DataFrame."""
    df = pd.DataFrame(summaries)
    preferred = [
        "name", "start", "end", "n_days", "years", "total_return", "cagr",
        "volatility", "sharpe", "sortino", "max_drawdown", "calmar",
        "worst_day", "best_day", "worst_month", "best_month",
        "pct_positive_days", "pct_positive_months",
    ]
    cols = [c for c in preferred if c in df.columns]
    cols += [c for c in df.columns if c not in cols]
    return df[cols]
