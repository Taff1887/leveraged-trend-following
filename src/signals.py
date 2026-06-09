"""
signals.py
==========

The trend signal. This is the heart of the Faber-style rule and of our
leveraged variant. The signal answers one question each day:

    Is the S&P 500 total-return index ABOVE or BELOW its moving average?

* ABOVE  -> signal = 1  ("good trend" / risk-on)
* BELOW  -> signal = 0  ("bad trend"  / our leveraged re-entry zone)

The single most important detail for honesty is avoiding LOOK-AHEAD BIAS:
we can only act on information we actually had. So the position we hold on day t
must be decided using the signal computed at the *close of day t-1*. The
:func:`lagged_signal` function shifts the signal forward by one day to enforce
this.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def moving_average(prices: pd.Series, window: int) -> pd.Series:
    """Simple moving average (SMA) of the last ``window`` observations."""
    return prices.rolling(window=window, min_periods=window).mean()


def trend_signal(prices: pd.Series, window: int) -> pd.Series:
    """Raw daily trend signal: 1 if price > its SMA, else 0.

    The first ``window`` days have no full average, so the signal is NaN there
    and those days are simply excluded from the backtest.
    """
    sma = moving_average(prices, window)
    sig = (prices > sma).astype(float)
    sig[sma.isna()] = np.nan
    return sig


def lagged_signal(prices: pd.Series, window: int) -> pd.Series:
    """The signal we are allowed to TRADE on, shifted one day to avoid look-ahead.

    ``lagged_signal[t]`` equals ``trend_signal[t-1]``. So the position held on day
    t (and therefore the return we earn on day t) depends only on prices up to
    the close of day t-1.
    """
    return trend_signal(prices, window).shift(1)


def monthly_trend_signal(prices: pd.Series, months: int) -> pd.Series:
    """Faber's original monthly rule: compare the month-end price to its
    ``months``-month SMA, then hold that decision for the *whole next month*.

    Returns a DAILY signal so it can drive the same daily backtest engine. There
    is no look-ahead: every day in calendar month *M* uses the decision computed
    at the close of month *M − 1* (which was fully known before month *M* began).

    Implementation note: we map each daily date to the signal of the *previous*
    calendar month explicitly (via month periods). This avoids the subtle
    double-lag you get from ``shift(1)`` on a month-end-labelled series followed
    by a forward-fill, which would make each month trade on data from *two*
    months prior.
    """
    monthly = prices.resample("ME").last()
    sma = monthly.rolling(months, min_periods=months).mean()
    monthly_sig = (monthly > sma).astype(float)
    monthly_sig[sma.isna()] = np.nan

    # Re-index the month-end decisions by calendar month (period 'M').
    sig_by_month = pd.Series(monthly_sig.values,
                             index=monthly_sig.index.to_period("M"))
    # Each daily date in month M should use the decision from month M-1.
    prev_month = prices.index.to_period("M") - 1
    daily_sig = pd.Series(sig_by_month.reindex(prev_month).values,
                          index=prices.index)
    return daily_sig


def signal_segments(signal: pd.Series) -> list[tuple]:
    """Group a 0/1 signal into contiguous runs.

    Returns a list of (start_date, end_date, value) tuples, useful for shading
    "in/out of market" regions on a chart.
    """
    s = signal.dropna()
    if s.empty:
        return []
    segments = []
    seg_start = s.index[0]
    seg_val = s.iloc[0]
    prev_date = s.index[0]
    for date, val in s.items():
        if val != seg_val:
            segments.append((seg_start, prev_date, seg_val))
            seg_start = date
            seg_val = val
        prev_date = date
    segments.append((seg_start, prev_date, seg_val))
    return segments
