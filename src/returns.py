"""
returns.py
==========

Tiny, transparent helpers for turning prices into returns and returns into a
cumulative wealth index. Everything here is a one- or two-line pandas operation.
We keep them as named functions so the rest of the code (and the reader) never
has to wonder "wait, is this a simple return or a log return?".

Definitions used throughout the project
----------------------------------------
* simple daily return:   r_t = P_t / P_{t-1} - 1
* log daily return:      l_t = ln(P_t / P_{t-1})
* cumulative index:      W_t = W_0 * prod(1 + r_i) for i = 1..t   (daily compounding)

We compound SIMPLE returns multiplicatively, which is exactly how money grows in
a real account that is rebalanced daily. This is the mechanism that produces
"volatility decay" for leveraged exposure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def simple_returns(prices: pd.Series) -> pd.Series:
    """Daily simple returns from a price (or total-return-index) series.

    The first observation has no prior day, so it becomes NaN and is dropped.
    """
    prices = prices.dropna()
    rets = prices.pct_change()
    return rets.dropna()


def log_returns(prices: pd.Series) -> pd.Series:
    """Daily log returns. Useful for some statistics; not used for compounding."""
    prices = prices.dropna()
    rets = np.log(prices / prices.shift(1))
    return rets.dropna()


def cumulative_index(returns: pd.Series, base: float = 1.0) -> pd.Series:
    """Grow ``base`` (e.g. $1) forward through a stream of simple returns.

    This is daily compounding: each day's wealth is the previous day's wealth
    times (1 + that day's return). The result is the strategy's equity curve.
    """
    returns = returns.fillna(0.0)
    return base * (1.0 + returns).cumprod()


def returns_from_index(index: pd.Series) -> pd.Series:
    """Inverse of :func:`cumulative_index` -- recover daily returns from a wealth curve."""
    return simple_returns(index)


def to_monthly_prices(prices: pd.Series) -> pd.Series:
    """Resample a daily price/index series to month-end (last observation)."""
    return prices.resample("ME").last().dropna()


def to_monthly_returns(returns: pd.Series) -> pd.Series:
    """Compound daily simple returns up to monthly simple returns."""
    returns = returns.fillna(0.0)
    return (1.0 + returns).resample("ME").prod() - 1.0


def annual_rate_to_daily(annual_rate: float) -> float:
    """Convert an annual rate (e.g. a T-bill yield of 0.04) to a daily rate.

    We use geometric (compounding) conversion so that compounding the daily rate
    over a year reproduces the annual rate exactly:
        (1 + daily) ** TRADING_DAYS = 1 + annual
    """
    from .config import TRADING_DAYS_PER_YEAR

    return (1.0 + annual_rate) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0


def daily_riskfree_from_rate_series(rate_pct: pd.Series) -> pd.Series:
    """Turn an annualized %-rate series (like ^IRX, quoted as 4.5 = 4.5%) into a
    daily simple risk-free return series, aligned to the rate's dates.

    ^IRX is quoted in *percent* (4.5 means 4.5% annual), so we divide by 100 first.
    """
    from .config import TRADING_DAYS_PER_YEAR

    annual = rate_pct.astype(float) / 100.0
    annual = annual.clip(lower=-0.99)  # guard against bad prints
    daily = (1.0 + annual) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
    return daily
