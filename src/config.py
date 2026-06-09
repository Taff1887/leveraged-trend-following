"""
config.py
=========

Central configuration for the project. Every other module imports from here so
that paths, parameters, and assumptions live in ONE place. If you want to change
the leverage levels, the moving-average windows, or the cost assumptions, this
is the only file you need to edit.

The philosophy of this whole repo is: keep it simple and explicit. Nothing here
is clever. It is just a list of the choices we made, written down so a reader can
see them all at once.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Project paths
# ---------------------------------------------------------------------------
# PROJECT_ROOT is the top-level folder of the repository (one level above /src).
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"            # untouched downloads (one CSV per ticker)
PROCESSED_DATA_DIR = DATA_DIR / "processed"  # cleaned / aligned data
CHARTS_DIR = PROJECT_ROOT / "charts"        # all figures (.png) are saved here
RESULTS_DIR = PROJECT_ROOT / "results"      # all result tables (.csv/.json) are saved here
REPORTS_DIR = PROJECT_ROOT / "reports"      # the research paper and executive summary

# Make sure the output folders exist (cheap, idempotent).
for _d in (RAW_DATA_DIR, PROCESSED_DATA_DIR, CHARTS_DIR, RESULTS_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 2. Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED = 20260609  # fixed seed -> Monte Carlo and synthetic data are reproducible


# ---------------------------------------------------------------------------
# 3. Calendar constants
# ---------------------------------------------------------------------------
TRADING_DAYS_PER_YEAR = 252   # standard convention for annualizing daily numbers
MONTHS_PER_YEAR = 12

# Trading-day equivalents of "month-based" moving averages used by Faber.
# A month has ~21 trading days, so:
#   10-month SMA  ~= 210 trading days
#   12-month SMA  ~= 252 trading days
TRADING_DAYS_PER_MONTH = 21


# ---------------------------------------------------------------------------
# 4. Strategy parameter grids
# ---------------------------------------------------------------------------
# Moving-average windows (in *trading days*). We label the monthly equivalents so
# the reader can connect them back to the classic Faber 10-month rule.
MA_WINDOWS = [50, 100, 150, 200, 210, 250, 252]

# Human-readable labels for each window (used in tables and chart axes).
MA_WINDOW_LABELS = {
    50: "50d",
    100: "100d",
    150: "150d",
    200: "200d (~9.5mo)",
    210: "210d (10mo)",
    250: "250d",
    252: "252d (12mo)",
}

# Leverage levels to test when the market is BELOW its moving average.
LEVERAGE_LEVELS = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]


# ---------------------------------------------------------------------------
# 5. Cost assumptions
# ---------------------------------------------------------------------------
# All costs are expressed as ANNUAL rates unless noted. The backtest converts
# them to a daily drag. We start every analysis with ZERO costs (the "gross"
# base case) and then re-run with these realistic costs as a sensitivity.
#
# Why these numbers?
#   - expense_ratio_1x:   a cheap S&P 500 ETF (e.g. SPY/VOO/IVV) costs ~0.03%-0.09%.
#   - expense_ratio_lev:  leveraged ETFs (SSO/UPRO/SPXL) charge ~0.90%-0.95%.
#   - financing_spread:   leverage is borrowed money; brokers/swaps charge the
#                         risk-free rate PLUS a spread. We use ~0.50% spread.
#   - transaction_cost:   cost paid each time we switch position (round-trip),
#                         covering commissions + bid/ask. Expressed per switch.
#   - slippage:           extra execution cost, optional, per switch.
DEFAULT_COSTS = {
    "expense_ratio_1x": 0.0009,     # 0.09% per year on the 1x sleeve
    "expense_ratio_lev": 0.0095,    # 0.95% per year on the leveraged sleeve
    "financing_spread": 0.0050,     # 0.50% per year above the risk-free rate
    "transaction_cost": 0.0005,     # 0.05% (5 bps) charged on turnover when switching
    "slippage": 0.0000,             # extra execution cost per switch (off by default)
    "apply_financing": True,        # charge (L-1) * (rf + spread) on the borrowed part
    "apply_expense": True,          # charge the expense ratio drag
    "apply_transaction": True,      # charge transaction cost on position switches
}

# A convenient "zero cost" dictionary for the gross base case.
ZERO_COSTS = {
    "expense_ratio_1x": 0.0,
    "expense_ratio_lev": 0.0,
    "financing_spread": 0.0,
    "transaction_cost": 0.0,
    "slippage": 0.0,
    "apply_financing": False,
    "apply_expense": False,
    "apply_transaction": False,
}

# If we cannot find a real T-bill series, fall back to this constant annual
# risk-free rate. It is only a fallback; the code prefers real ^IRX data.
FALLBACK_RISK_FREE_RATE = 0.02  # 2% per year


# ---------------------------------------------------------------------------
# 6. Tickers / data universe
# ---------------------------------------------------------------------------
# This registry is the single source of truth for every series we load. To add a
# new ETF, just add a row here -- the loader, cleaner, and ETF tests all read
# from this dict, so nothing else needs to change.
#
# Fields:
#   role        : "underlying" (the index we time), "rf" (risk-free),
#                 "proxy_1x", "leveraged" (real leveraged ETF), "context".
#   leverage    : the daily leverage multiple the ETF targets (1x, 2x, 3x).
#   kind        : "total_return", "adjusted_price", or "price_only" / "rate".
#   expense     : ETF expense ratio (annual), where applicable.
#   note        : short human description.
TICKERS = {
    # --- The series we actually time and treat as "the S&P 500 total return" ---
    "^SP500TR": {
        "role": "underlying",
        "leverage": 1.0,
        "kind": "total_return",
        "expense": 0.0,
        "note": "S&P 500 Total Return index (dividends reinvested). True daily TR, ~1988+.",
    },
    # --- Investable 1x proxies (total return via adjusted close) ---
    "SPY": {
        "role": "proxy_1x",
        "leverage": 1.0,
        "kind": "adjusted_price",
        "expense": 0.0945,  # note: SPY expense is 0.0945%; stored as percent-of-1? see below
        "note": "SPDR S&P 500 ETF, 1x. Adjusted close = total return. 1993+.",
    },
    "VOO": {
        "role": "proxy_1x",
        "leverage": 1.0,
        "kind": "adjusted_price",
        "expense": 0.0003,
        "note": "Vanguard S&P 500 ETF, 1x. 2010+.",
    },
    "IVV": {
        "role": "proxy_1x",
        "leverage": 1.0,
        "kind": "adjusted_price",
        "expense": 0.0003,
        "note": "iShares Core S&P 500 ETF, 1x. 2000+.",
    },
    "SPLG": {
        "role": "proxy_1x",
        "leverage": 1.0,
        "kind": "adjusted_price",
        "expense": 0.0002,
        "note": "SPDR Portfolio S&P 500 ETF, 1x. 2005+.",
    },
    # --- Real leveraged S&P 500 ETFs ---
    "SSO": {
        "role": "leveraged",
        "leverage": 2.0,
        "kind": "adjusted_price",
        "expense": 0.0091,
        "note": "ProShares Ultra S&P500, daily 2x. 2006+.",
    },
    "UPRO": {
        "role": "leveraged",
        "leverage": 3.0,
        "kind": "adjusted_price",
        "expense": 0.0091,
        "note": "ProShares UltraPro S&P500, daily 3x. 2009+.",
    },
    "SPXL": {
        "role": "leveraged",
        "leverage": 3.0,
        "kind": "adjusted_price",
        "expense": 0.0091,
        "note": "Direxion Daily S&P 500 Bull 3X, daily 3x. 2008+.",
    },
    # --- Long-history context (price only, no dividends) ---
    "^GSPC": {
        "role": "context",
        "leverage": 1.0,
        "kind": "price_only",
        "expense": 0.0,
        "note": "S&P 500 price index (NO dividends). Long history ~1927+. Context only.",
    },
    # --- Risk-free / financing rate ---
    "^IRX": {
        "role": "rf",
        "leverage": 0.0,
        "kind": "rate",
        "expense": 0.0,
        "note": "13-week US T-bill discount rate (annualized %). Used for cash + financing.",
    },
}

# NOTE on the SPY expense value above: expense ratios in this dict are stored as
# DECIMAL fractions per year (e.g. 0.0091 = 0.91%). SPY's true expense is 0.0945%
# = 0.000945. We override the few proxy 1x expenses to their decimal form here so
# nobody has to remember the convention:
TICKERS["SPY"]["expense"] = 0.000945
TICKERS["VOO"]["expense"] = 0.00003
TICKERS["IVV"]["expense"] = 0.00003
TICKERS["SPLG"]["expense"] = 0.00002

# Convenience groupings.
PROXY_1X_TICKERS = [t for t, m in TICKERS.items() if m["role"] == "proxy_1x"]
LEVERAGED_ETF_TICKERS = [t for t, m in TICKERS.items() if m["role"] == "leveraged"]
DEFAULT_UNDERLYING = "^SP500TR"   # what we treat as "the S&P 500 total return"
RISK_FREE_TICKER = "^IRX"


# ---------------------------------------------------------------------------
# 7. Data download window
# ---------------------------------------------------------------------------
DATA_START = "1900-01-01"   # ask for everything; the source decides the real start
DATA_END = None             # None => up to the latest available date


# ---------------------------------------------------------------------------
# 8. Period / regime definitions for Part 5
# ---------------------------------------------------------------------------
# "Onward" periods: each entry is (label, start_date, end_date_or_None).
PERIODS = [
    ("Full sample", None, None),
    ("1950 onward", "1950-01-01", None),
    ("1970 onward", "1970-01-01", None),
    ("1980 onward", "1980-01-01", None),
    ("1990 onward", "1990-01-01", None),
    ("2000 onward", "2000-01-01", None),
    ("2010 onward", "2010-01-01", None),
    ("Post-GFC (2009+)", "2009-07-01", None),
    ("Post-COVID (2020-04+)", "2020-04-01", None),
]

# Specific historical episodes (stress windows). Some will only have data when
# using the long ^GSPC price index; the code skips any episode with no data.
EPISODES = [
    ("1929 crash", "1929-08-01", "1932-12-31"),
    ("1970s inflation bear", "1973-01-01", "1974-12-31"),
    ("1987 crash", "1987-08-01", "1988-06-30"),
    ("Dot-com crash", "2000-03-01", "2002-12-31"),
    ("Global Financial Crisis", "2007-10-01", "2009-06-30"),
    ("COVID crash", "2020-02-01", "2020-06-30"),
    ("2022 rate-hike bear", "2022-01-01", "2022-12-31"),
]


# ---------------------------------------------------------------------------
# 9. Monte Carlo grids for Part 7
# ---------------------------------------------------------------------------
MC_ANNUAL_DRIFTS = [0.00, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20]
MC_ANNUAL_VOLS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60]
MC_LEVERAGES = LEVERAGE_LEVELS                # reuse the same leverage grid
MC_HORIZONS_YEARS = [1, 3, 5, 10, 20]
MC_N_PATHS = 10_000                            # default number of simulated paths

# A smaller, faster set used by notebooks / quick demos so they run in seconds.
MC_N_PATHS_FAST = 2_000


# ---------------------------------------------------------------------------
# 10. Matplotlib / chart settings
# ---------------------------------------------------------------------------
CHART_DPI = 130
CHART_STYLE = "seaborn-v0_8-whitegrid"  # falls back gracefully if unavailable

# A small, colour-blind-friendly palette reused across the project.
COLORS = {
    "buy_hold": "#1f77b4",     # blue
    "ma_cash": "#2ca02c",      # green
    "leveraged": "#d62728",    # red
    "benchmark": "#7f7f7f",    # grey
    "accent": "#ff7f0e",       # orange
    "neutral": "#9467bd",      # purple
}


def costs_with(**overrides) -> dict:
    """Return a copy of DEFAULT_COSTS with the given keys overridden.

    Handy for sensitivity runs, e.g. ``costs_with(transaction_cost=0.001)``.
    """
    c = dict(DEFAULT_COSTS)
    c.update(overrides)
    return c
