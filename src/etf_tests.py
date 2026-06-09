"""
etf_tests.py
============

Reality check. The synthetic-leverage backtest assumes you can earn exactly
``L * (daily S&P 500 return)`` every day forever. Real leveraged ETFs (SSO 2x,
UPRO/SPXL 3x) only approximately do that: they charge ~0.9% expense, pay
financing on the borrowed money, and have tracking error / path dependency.

This module quantifies the gap by:

1. Building a SYNTHETIC daily-leverage return stream from the 1x underlying.
2. Comparing it to the REAL leveraged-ETF return stream over the same dates.
3. Reporting realized leverage (beta), tracking error, and the annual return gap
   so we can say whether synthetic leverage OVER- or UNDER-states reality.

It also rebuilds our core strategy using REAL ETF returns in the bad-market
sleeve, so we can compare "paper" performance with what an investor could
actually have captured.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .returns import simple_returns, cumulative_index, annual_rate_to_daily
from .metrics import summarize
from .backtest import run_exposure_strategy
from .signals import lagged_signal


def synthetic_leverage_returns(underlying_returns: pd.Series, leverage: float,
                               rf_daily=0.0, expense_annual: float = 0.0,
                               financing_spread: float = 0.0,
                               model_costs: bool = False) -> pd.Series:
    """Synthetic daily-leveraged return stream from the 1x underlying.

    If ``model_costs`` is True we subtract the same expense + financing a real ETF
    would pay, which makes the comparison to a real ETF fair (this isolates pure
    tracking error). If False, we return the idealised ``leverage * return``.
    """
    r = leverage * underlying_returns
    if model_costs:
        if isinstance(rf_daily, (int, float)):
            rf = pd.Series(float(rf_daily), index=underlying_returns.index)
        else:
            rf = rf_daily.reindex(underlying_returns.index).ffill().fillna(0.0)
        spread_d = annual_rate_to_daily(financing_spread)
        financing = max(leverage - 1.0, 0.0) * (rf + spread_d)
        exp_d = (1.0 + expense_annual) ** (1.0 / config.TRADING_DAYS_PER_YEAR) - 1.0
        r = r - financing - exp_d
    return r.rename(f"synthetic_{leverage:g}x")


def compare_synthetic_vs_real(underlying_returns: pd.Series, etf_returns: pd.Series,
                              leverage: float, rf_daily=0.0,
                              expense_annual: float = 0.0,
                              financing_spread: float = None) -> dict:
    """Compare synthetic L-times leverage to a real leveraged ETF over common dates.

    Returns a dict of comparison statistics plus the two cumulative curves.
    """
    if financing_spread is None:
        financing_spread = config.DEFAULT_COSTS["financing_spread"]

    # Align on the dates both series have.
    df = pd.concat([underlying_returns, etf_returns], axis=1, join="inner").dropna()
    df.columns = ["underlying", "etf"]
    u = df["underlying"]
    etf = df["etf"]

    synth_gross = synthetic_leverage_returns(u, leverage, model_costs=False)
    synth_costed = synthetic_leverage_returns(
        u, leverage, rf_daily=rf_daily, expense_annual=expense_annual,
        financing_spread=financing_spread, model_costs=True)

    # Realized leverage = slope of ETF daily returns on underlying daily returns.
    cov = np.cov(etf.values, u.values)[0, 1]
    var_u = np.var(u.values, ddof=1)
    realized_beta = cov / var_u if var_u > 0 else np.nan

    # Tracking error of the ETF vs the COSTED synthetic (annualized std of diff).
    diff = etf - synth_costed
    tracking_error = diff.std(ddof=1) * np.sqrt(config.TRADING_DAYS_PER_YEAR)

    etf_cagr = (1 + etf).prod() ** (config.TRADING_DAYS_PER_YEAR / len(etf)) - 1
    synth_gross_cagr = (1 + synth_gross).prod() ** (
        config.TRADING_DAYS_PER_YEAR / len(synth_gross)) - 1
    synth_costed_cagr = (1 + synth_costed).prod() ** (
        config.TRADING_DAYS_PER_YEAR / len(synth_costed)) - 1

    return {
        "leverage": leverage,
        "start": df.index.min(),
        "end": df.index.max(),
        "n_days": len(df),
        "realized_beta": realized_beta,
        "tracking_error_ann": tracking_error,
        "etf_cagr": etf_cagr,
        "synthetic_gross_cagr": synth_gross_cagr,
        "synthetic_costed_cagr": synth_costed_cagr,
        "gap_gross_minus_etf": synth_gross_cagr - etf_cagr,
        "gap_costed_minus_etf": synth_costed_cagr - etf_cagr,
        "correlation": etf.corr(u),
        "curves": {
            "underlying (1x)": cumulative_index(u),
            f"real ETF ({leverage:g}x)": cumulative_index(etf),
            f"synthetic {leverage:g}x (gross)": cumulative_index(synth_gross),
            f"synthetic {leverage:g}x (costed)": cumulative_index(synth_costed),
        },
    }


def strategy_with_real_etf(prices: pd.Series, underlying_returns: pd.Series,
                           etf_returns: pd.Series, window: int, leverage: float,
                           rf_daily=0.0) -> dict:
    """Rebuild the leveraged-bad-market strategy using REAL ETF returns below the MA.

    Above the MA: earn the 1x underlying return.
    Below the MA: earn the REAL leveraged-ETF return (fees, tracking error and all).

    Returns a dict with both the 'real-ETF' strategy and the matched synthetic
    strategy over the same common window, so they can be compared directly.
    """
    # Common window where we have prices, underlying, and the ETF.
    df = pd.concat([prices.rename("px"), underlying_returns.rename("u"),
                    etf_returns.rename("etf")], axis=1, join="inner").dropna()
    px = df["px"]
    u = df["u"]
    etf = df["etf"]

    sig = lagged_signal(px, window)            # 1 above MA, 0 below MA, lagged
    sig = sig.reindex(df.index)

    # Real-ETF strategy daily return: pick underlying when above, ETF when below.
    real_ret = u.where(sig == 1.0, etf)
    real_ret = real_ret[sig.notna()]
    real_equity = cumulative_index(real_ret)

    # Matched synthetic strategy on the SAME window via the standard engine.
    exposure = sig.map({1.0: 1.0, 0.0: leverage})
    synth_res = run_exposure_strategy(u, exposure, rf_daily=rf_daily,
                                      costs=config.ZERO_COSTS,
                                      name=f"synthetic {leverage:g}x strat")

    return {
        "window": window,
        "leverage": leverage,
        "real": {
            "returns": real_ret,
            "equity": real_equity,
            "summary": summarize(real_ret, name=f"real-ETF {leverage:g}x strat"),
        },
        "synthetic": {
            "returns": synth_res.net_returns,
            "equity": synth_res.equity,
            "summary": synth_res.summary(),
        },
    }


def etf_returns_from_prices(level_series: pd.Series) -> pd.Series:
    """Convenience: daily simple returns from a (cleaned) ETF level series."""
    return simple_returns(level_series)
