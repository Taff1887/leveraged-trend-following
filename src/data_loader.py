"""
data_loader.py
==============

Gets the price/return data we need and CACHES it to ``data/raw`` so we only hit
the internet once. The design goals are:

1. Reproducible: prefer simple public sources (Yahoo Finance via ``yfinance``).
2. Robust: retry on rate limits, and fall back to a clearly-labelled SYNTHETIC
   series if the network is unavailable, so the whole pipeline always runs.
3. Honest: every series we return carries a ``source`` and ``kind`` label so the
   data-summary table can tell the reader exactly what they are looking at.

The two real long-history total-return options we use are:
* ``^SP500TR`` -- the S&P 500 Total Return index (true daily TR), from ~1988.
* ``SPY`` adjusted close -- an investable proxy whose adjusted close equals total
  return, from 1993.

For very long context we also load ``^GSPC`` (the price index, NO dividends,
from ~1927), which we clearly label as price-only.
"""

from __future__ import annotations

import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

warnings.filterwarnings("ignore", category=FutureWarning)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
def _safe_name(ticker: str) -> str:
    """Make a filesystem-safe filename from a ticker (e.g. '^SP500TR' -> 'SP500TR')."""
    return ticker.replace("^", "").replace("/", "_").replace(" ", "_")


def _cache_path(ticker: str) -> Path:
    return config.RAW_DATA_DIR / f"{_safe_name(ticker)}.csv"


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------
def _download_yf(ticker: str, start: str | None, end: str | None,
                 max_retries: int = 4, pause: float = 2.0) -> pd.DataFrame | None:
    """Download one ticker from Yahoo Finance with simple retry/backoff.

    Returns a DataFrame with columns like 'Open','High','Low','Close','Adj Close',
    'Volume', or None if every attempt failed.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None

    for attempt in range(1, max_retries + 1):
        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if df is not None and len(df) > 0:
                # Single-ticker downloads can come back with a MultiIndex column
                # like ('Adj Close','SPY'); flatten to just the field name.
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.index = pd.to_datetime(df.index)
                df = df[~df.index.duplicated(keep="last")].sort_index()
                return df
        except Exception as exc:  # network error / rate limit / etc.
            print(f"  [{ticker}] attempt {attempt}/{max_retries} failed: "
                  f"{type(exc).__name__}: {str(exc)[:80]}")
        time.sleep(pause * attempt)  # linear backoff
    return None


def fetch_ticker(ticker: str, start: str | None = None, end: str | None = None,
                 force: bool = False) -> pd.DataFrame | None:
    """Return raw OHLC(+Adj Close) data for ``ticker``, using the CSV cache.

    If a cache file exists and ``force`` is False, we read it. Otherwise we try to
    download and then save the result to the cache.
    """
    start = start or config.DATA_START
    end = end or config.DATA_END
    path = _cache_path(ticker)

    if path.exists() and not force:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if len(df) > 0:
            return df

    df = _download_yf(ticker, start, end)
    if df is not None and len(df) > 0:
        df.to_csv(path)
        return df

    # Could not download and no cache -> signal failure to the caller.
    if path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True)
    return None


# ---------------------------------------------------------------------------
# Turning raw OHLC into the single level series we care about
# ---------------------------------------------------------------------------
def extract_level(df: pd.DataFrame, ticker: str) -> pd.Series:
    """Pick the right column to use as the 'level' for a ticker.

    * rate series (^IRX)            -> the 'Close' (the quoted rate, in %).
    * everything else              -> 'Adj Close' if present, else 'Close'.
      For total-return / price-only indices, Adj Close == Close anyway.
    """
    meta = config.TICKERS.get(ticker, {})
    if meta.get("kind") == "rate":
        col = "Close" if "Close" in df.columns else df.columns[0]
        return df[col].astype(float).rename(ticker)

    if "Adj Close" in df.columns:
        col = "Adj Close"
    elif "Close" in df.columns:
        col = "Close"
    else:
        col = df.columns[0]
    return df[col].astype(float).rename(ticker)


def get_level_series(ticker: str, force: bool = False) -> pd.Series | None:
    """High-level helper: cached level series for a ticker, or None if unavailable."""
    df = fetch_ticker(ticker, force=force)
    if df is None or len(df) == 0:
        return None
    s = extract_level(df, ticker).dropna()
    return s if len(s) else None


def load_universe(tickers: list[str] | None = None, force: bool = False) -> dict:
    """Load level series for many tickers. Returns ``{ticker: Series}``.

    Missing tickers are simply omitted (with a printed note) so a single failed
    download never breaks the whole run.
    """
    tickers = tickers or list(config.TICKERS.keys())
    out = {}
    for t in tickers:
        s = get_level_series(t, force=force)
        if s is not None:
            out[t] = s
        else:
            print(f"  [warn] no data for {t} (download failed and no cache).")
    return out


# ---------------------------------------------------------------------------
# Synthetic fallback (so the repo always runs, even offline)
# ---------------------------------------------------------------------------
def make_synthetic_sp500(start: str = "1990-01-01", end: str = "2026-06-05",
                         seed: int | None = None) -> pd.Series:
    """Generate a realistic SYNTHETIC daily S&P 500 total-return INDEX.

    This is NOT real data. It is a regime-switching random walk used only when no
    real data is available (offline) and as a sanity check for the Monte Carlo
    section. It has the qualitative features that matter for our question:

    * a long-run upward drift,
    * calm "bull" regimes (low volatility, positive drift),
    * occasional "bear" regimes (high volatility, negative drift),
    * fat tails (Student-t shocks) so crashes are not impossibly rare.

    The series is fully reproducible from ``config.RANDOM_SEED``.
    """
    seed = config.RANDOM_SEED if seed is None else seed
    rng = np.random.default_rng(seed)

    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)

    # Daily parameters for the two regimes (annual -> daily).
    td = config.TRADING_DAYS_PER_YEAR
    bull = {"mu": 0.13 / td, "sigma": 0.13 / np.sqrt(td)}
    bear = {"mu": -0.18 / td, "sigma": 0.32 / np.sqrt(td)}
    # Expected regime lengths: ~bull 2 years, bear ~6 months.
    p_stay_bull = 1.0 - 1.0 / (2.0 * td)
    p_stay_bear = 1.0 - 1.0 / (0.5 * td)

    state = 0  # 0 = bull, 1 = bear
    rets = np.empty(n)
    nu = 5.0  # Student-t degrees of freedom (fat tails)
    for i in range(n):
        if state == 0:
            mu, sigma = bull["mu"], bull["sigma"]
            if rng.random() > p_stay_bull:
                state = 1
        else:
            mu, sigma = bear["mu"], bear["sigma"]
            if rng.random() > p_stay_bear:
                state = 0
        shock = rng.standard_t(nu) / np.sqrt(nu / (nu - 2.0))  # unit-variance t
        rets[i] = mu + sigma * shock

    index = 100.0 * np.cumprod(1.0 + rets)
    return pd.Series(index, index=dates, name="SYNTH_SP500TR")


# ---------------------------------------------------------------------------
# The canonical underlying total-return series (with documented fallbacks)
# ---------------------------------------------------------------------------
def get_underlying_total_return(force: bool = False) -> tuple[pd.Series, str, str]:
    """Return ``(series, ticker, source_label)`` for "the S&P 500 total return".

    Preference order (longest, truest daily total return first):
      1. ^SP500TR   -- true daily total return, ~1988+
      2. SPY        -- adjusted close = total return, 1993+
      3. SYNTHETIC  -- generated, clearly labelled, last resort (offline)
    """
    # 1. True total-return index.
    s = get_level_series(config.DEFAULT_UNDERLYING, force=force)
    if s is not None and len(s) > 500:
        return s, config.DEFAULT_UNDERLYING, "Yahoo Finance ^SP500TR (true daily total return)"

    # 2. SPY adjusted close.
    s = get_level_series("SPY", force=force)
    if s is not None and len(s) > 500:
        return s, "SPY", "Yahoo Finance SPY adjusted close (total-return proxy)"

    # 3. Synthetic fallback.
    s = make_synthetic_sp500()
    return s, "SYNTH_SP500TR", "SYNTHETIC regime-switching series (NO real data available)"


def get_risk_free_daily(index: pd.Index | None = None,
                        force: bool = False) -> pd.Series:
    """Daily risk-free return series from ^IRX (13-week T-bill), or a constant
    fallback if unavailable. Optionally reindexed/ffilled to ``index``.
    """
    from .returns import daily_riskfree_from_rate_series

    s = get_level_series(config.RISK_FREE_TICKER, force=force)
    if s is None:
        rf = config.FALLBACK_RISK_FREE_RATE
        daily = (1.0 + rf) ** (1.0 / config.TRADING_DAYS_PER_YEAR) - 1.0
        if index is None:
            return pd.Series(dtype=float)
        return pd.Series(daily, index=index)

    daily = daily_riskfree_from_rate_series(s)
    if index is not None:
        daily = daily.reindex(index).ffill().fillna(0.0)
    return daily.rename("rf_daily")
