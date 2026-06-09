"""
data_cleaning.py
================

Turns raw level series into clean, aligned data that the backtest can trust, and
produces the data-summary table the paper requires. The cleaning decisions are
deliberately conservative and ALL documented:

* Drop duplicate dates (keep the last print).
* Sort by date.
* Drop leading/trailing NaNs.
* Detect missing trading days (gaps in the business-day calendar).
* Forward-fill ONLY small interior gaps (<= ``max_ffill`` days), and only because
  a stale price for one or two days does not distort daily returns materially.
  We never forward-fill long gaps -- those are real data outages and we leave
  them visible.
* We do NOT fabricate dividends or back-fill history.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def clean_level_series(s: pd.Series, max_ffill: int = 3) -> tuple[pd.Series, dict]:
    """Clean a single level series and return ``(clean_series, report)``.

    The ``report`` dict records exactly what we did so the data-summary table and
    the paper can be honest about it.
    """
    raw_n = len(s)
    s = s.copy()

    # 1. Sort and de-duplicate dates.
    s = s.sort_index()
    n_dupes = int(s.index.duplicated().sum())
    s = s[~s.index.duplicated(keep="last")]

    # 2. Trim leading / trailing NaNs.
    s = s.loc[s.first_valid_index(): s.last_valid_index()]

    # 3. Count interior missing values BEFORE filling.
    n_missing_interior = int(s.isna().sum())

    # 4. Forward-fill only short interior gaps.
    if n_missing_interior > 0:
        s = s.ffill(limit=max_ffill)
    n_still_missing = int(s.isna().sum())
    s = s.dropna()

    # 5. Compare against a business-day calendar to spot missing trading days.
    if len(s) >= 2:
        full_bdays = pd.bdate_range(s.index.min(), s.index.max())
        missing_bdays = int(len(full_bdays) - len(s.index.intersection(full_bdays)))
    else:
        missing_bdays = 0

    report = {
        "raw_observations": raw_n,
        "clean_observations": len(s),
        "duplicate_dates_removed": n_dupes,
        "interior_nans_filled": n_missing_interior - n_still_missing,
        "nans_dropped": n_still_missing,
        "missing_business_days": missing_bdays,
        "first_date": s.index.min() if len(s) else pd.NaT,
        "last_date": s.index.max() if len(s) else pd.NaT,
    }
    return s, report


def align_series(series_dict: dict, how: str = "outer") -> pd.DataFrame:
    """Align several level series onto one DateTimeIndex.

    ``how='outer'`` keeps every date any series has (good for plotting different
    histories); ``how='inner'`` keeps only dates ALL series share (good for fair
    head-to-head comparisons over a common window).
    """
    frame = pd.concat(series_dict.values(), axis=1, join=how)
    frame.columns = list(series_dict.keys())
    return frame.sort_index()


def build_data_summary(series_dict: dict, reports: dict | None = None) -> pd.DataFrame:
    """Build the required data-summary table.

    Columns: ticker / name, first date, last date, # observations, missing
    observations, data source, and whether the series is total return, adjusted
    price, or price-only.
    """
    rows = []
    kind_label = {
        "total_return": "Total return",
        "adjusted_price": "Adjusted price (=TR)",
        "price_only": "Price only (no dividends)",
        "rate": "Interest rate (%)",
    }
    for ticker, s in series_dict.items():
        meta = config.TICKERS.get(ticker, {})
        rep = (reports or {}).get(ticker, {})
        rows.append({
            "ticker": ticker,
            "role": meta.get("role", "?"),
            "leverage": meta.get("leverage", np.nan),
            "first_date": s.index.min().date() if len(s) else None,
            "last_date": s.index.max().date() if len(s) else None,
            "n_observations": len(s),
            "missing_business_days": rep.get("missing_business_days", np.nan),
            "duplicates_removed": rep.get("duplicate_dates_removed", np.nan),
            "interior_filled": rep.get("interior_nans_filled", np.nan),
            "kind": kind_label.get(meta.get("kind", ""), meta.get("kind", "?")),
            "source": "Yahoo Finance" if not ticker.startswith("SYNTH")
                      else "Synthetic (generated)",
            "note": meta.get("note", ""),
        })
    df = pd.DataFrame(rows)
    return df.sort_values(["role", "ticker"]).reset_index(drop=True)


def clean_universe(series_dict: dict, max_ffill: int = 3) -> tuple[dict, dict]:
    """Clean every series in a universe. Returns ``(clean_dict, reports_dict)``."""
    clean = {}
    reports = {}
    for ticker, s in series_dict.items():
        cs, rep = clean_level_series(s, max_ffill=max_ffill)
        clean[ticker] = cs
        reports[ticker] = rep
    return clean, reports
