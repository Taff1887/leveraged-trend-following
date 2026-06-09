"""
backtest.py
===========

A from-scratch daily backtester. No frameworks, no hidden magic -- just one
vectorised function that turns (a) the underlying's daily returns and (b) a
per-day "exposure" schedule into a net daily return stream.

The single core idea
--------------------
Each day we hold some EXPOSURE ``e[t]`` to the S&P 500 total-return index:

    e[t] = 1.0   -> normal, fully invested in 1x S&P 500
    e[t] = 0.0   -> in cash (earns the risk-free rate)
    e[t] = 2.0   -> daily 2x leveraged exposure (borrow 1 unit)

The exposure is chosen by a trading rule and is always based on yesterday's
information (the signal is lagged), so there is no look-ahead bias.

Net daily return (the money equation)
-------------------------------------
    market   = e[t] * u[t]                         # leveraged market move
    cash     = max(1 - e[t], 0) * rf[t]            # idle capital earns cash
    financing= max(e[t] - 1, 0) * (rf[t] + spread) # borrowed part pays interest
    expense  = daily expense-ratio drag of the sleeve we hold
    txn      = (cost + slippage) * |e[t] - e[t-1]| # paid only when we trade
    net[t]   = market + cash - financing - expense - txn

Then we compound ``net`` daily to get the equity curve. Because we compound the
*leveraged* daily returns, volatility decay is captured automatically -- we do
not model it separately, it just happens.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .returns import annual_rate_to_daily, cumulative_index
from .signals import lagged_signal, monthly_trend_signal
from .metrics import summarize


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------
@dataclass
class StrategyResult:
    """Everything produced by a single backtest run."""

    name: str
    net_returns: pd.Series           # daily net simple returns (after costs)
    gross_returns: pd.Series         # daily returns before costs
    exposure: pd.Series              # the leverage/exposure held each day
    equity: pd.Series                # net equity curve (starts at 1.0)
    n_switches: int                  # how many times exposure changed
    meta: dict = field(default_factory=dict)

    def summary(self, rf_daily=0.0) -> dict:
        s = summarize(self.net_returns, rf_daily=rf_daily, name=self.name)
        s["n_switches"] = self.n_switches
        s.update(self.meta)
        return s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _expense_for_exposure(e: float, costs: dict) -> float:
    """Pick the right annual expense ratio for a given exposure level."""
    if e > 1.0:
        return costs.get("expense_ratio_lev", 0.0)
    if e == 1.0:
        return costs.get("expense_ratio_1x", 0.0)
    return 0.0  # pure cash has no fund expense


def _align_rf(rf_daily, index) -> pd.Series:
    """Coerce a risk-free input (scalar or Series) to a Series on ``index``."""
    if isinstance(rf_daily, pd.Series):
        return rf_daily.reindex(index).ffill().fillna(0.0)
    return pd.Series(float(rf_daily), index=index)


# ---------------------------------------------------------------------------
# The core engine
# ---------------------------------------------------------------------------
def run_exposure_strategy(
    underlying_returns: pd.Series,
    exposure: pd.Series,
    rf_daily=0.0,
    costs: dict | None = None,
    name: str = "strategy",
    meta: dict | None = None,
) -> StrategyResult:
    """Run a backtest given an explicit daily exposure schedule.

    Parameters
    ----------
    underlying_returns : daily simple returns of the S&P 500 total-return index.
    exposure           : daily exposure ``e[t]`` aligned to ``underlying_returns``.
                         MUST already be lagged (decided from yesterday's data).
    rf_daily           : daily risk-free rate (scalar or Series).
    costs              : a cost dict (see config). Defaults to ZERO_COSTS.
    """
    costs = dict(config.ZERO_COSTS if costs is None else costs)

    # Align everything to the days where we both have a return and an exposure.
    df = pd.DataFrame({"u": underlying_returns, "e": exposure}).dropna()
    if df.empty:
        raise ValueError("No overlapping data between returns and exposure.")
    u = df["u"]
    e = df["e"]
    rf = _align_rf(rf_daily, df.index)

    # --- Gross return: leveraged market move + cash on any idle capital ---
    market = e * u
    cash = (1.0 - e).clip(lower=0.0) * rf
    gross = market + cash

    # --- Costs (each toggled on/off via the costs dict) ---
    net = gross.copy()

    if costs.get("apply_financing", False):
        spread_daily = annual_rate_to_daily(costs.get("financing_spread", 0.0))
        financing = (e - 1.0).clip(lower=0.0) * (rf + spread_daily)
        net = net - financing

    if costs.get("apply_expense", False):
        # Expense ratio depends on which sleeve we hold each day.
        exp_annual = e.map(lambda x: _expense_for_exposure(x, costs))
        exp_daily = (1.0 + exp_annual) ** (1.0 / config.TRADING_DAYS_PER_YEAR) - 1.0
        net = net - exp_daily

    # Count switches (any change in exposure from one day to the next).
    delta = e.diff().abs().fillna(0.0)
    n_switches = int((delta > 1e-12).sum())

    if costs.get("apply_transaction", False):
        per_unit = costs.get("transaction_cost", 0.0) + costs.get("slippage", 0.0)
        txn = per_unit * delta  # cost proportional to the size of the exposure change
        net = net - txn

    equity = cumulative_index(net)
    result = StrategyResult(
        name=name,
        net_returns=net,
        gross_returns=gross,
        exposure=e,
        equity=equity,
        n_switches=n_switches,
        meta=dict(meta or {}),
    )
    return result


# ---------------------------------------------------------------------------
# Convenience wrappers for the three strategies in the paper
# ---------------------------------------------------------------------------
def buy_and_hold(underlying_returns: pd.Series, rf_daily=0.0,
                 costs: dict | None = None, name: str = "Buy & Hold 1x") -> StrategyResult:
    """Always 100% invested in 1x S&P 500 total return."""
    exposure = pd.Series(1.0, index=underlying_returns.index)
    return run_exposure_strategy(underlying_returns, exposure, rf_daily, costs, name)


def ma_to_cash(prices: pd.Series, underlying_returns: pd.Series, window: int,
               rf_daily=0.0, costs: dict | None = None,
               monthly: bool = False) -> StrategyResult:
    """Classic Faber-style rule: 1x when above the MA, cash when below.

    ``prices`` is the level series used to compute the signal (the TR index).
    """
    if monthly:
        # ``window`` is given in trading days everywhere; convert to whole months
        # for the monthly rule (e.g. 210d -> 10 months, 252d -> 12 months).
        months = max(1, round(window / config.TRADING_DAYS_PER_MONTH))
        sig = monthly_trend_signal(prices, months)
        label = f"MA->Cash ({months}mo)"
    else:
        sig = lagged_signal(prices, window)
        label = f"MA->Cash ({window}d)"
    # Above MA (sig==1) -> exposure 1; below (sig==0) -> exposure 0 (cash).
    exposure = sig.copy()  # already 1/0 and lagged
    res = run_exposure_strategy(underlying_returns, exposure, rf_daily, costs, label)
    res.meta.update({"window": window, "leverage_below": 0.0, "strategy": "ma_to_cash"})
    return res


def leveraged_bad_market(prices: pd.Series, underlying_returns: pd.Series,
                         window: int, leverage: float, rf_daily=0.0,
                         costs: dict | None = None,
                         monthly: bool = False) -> StrategyResult:
    """OUR strategy: 1x when above the MA, ``leverage``x when below the MA.

    The hypothesis is that weak-trend periods are disproportionately followed by
    strong rebounds, so adding leverage *there* might capture the recovery -- if
    volatility decay and deeper drawdowns don't eat the gains first.
    """
    if monthly:
        months = max(1, round(window / config.TRADING_DAYS_PER_MONTH))
        sig = monthly_trend_signal(prices, months)
        label = f"Lev {leverage:g}x below ({months}mo)"
    else:
        sig = lagged_signal(prices, window)
        label = f"Lev {leverage:g}x below ({window}d)"
    # sig==1 (above) -> exposure 1.0 ; sig==0 (below) -> exposure = leverage.
    exposure = sig.map({1.0: 1.0, 0.0: leverage})
    res = run_exposure_strategy(underlying_returns, exposure, rf_daily, costs, label)
    res.meta.update({"window": window, "leverage_below": leverage,
                     "strategy": "leveraged_bad_market"})
    return res


def leveraged_above_ma(prices: pd.Series, underlying_returns: pd.Series,
                       window: int, leverage: float, rf_daily=0.0,
                       costs: dict | None = None,
                       monthly: bool = False) -> StrategyResult:
    """INVERTED strategy: ``leverage``x when ABOVE the MA, 1x when BELOW it.

    This is the volatility-aware mirror image of :func:`leveraged_bad_market`.
    Faber's own data shows below-trend periods have ~60% lower returns and ~30%
    higher volatility, so this rule concentrates leverage in the calm, rising
    (above-trend) regime where leverage is rewarded, and de-risks to plain 1x in
    the volatile, falling (below-trend) regime where volatility decay bites.
    """
    if monthly:
        months = max(1, round(window / config.TRADING_DAYS_PER_MONTH))
        sig = monthly_trend_signal(prices, months)
        label = f"Lev {leverage:g}x above ({months}mo)"
    else:
        sig = lagged_signal(prices, window)
        label = f"Lev {leverage:g}x above ({window}d)"
    # sig==1 (above) -> exposure = leverage ; sig==0 (below) -> exposure 1.0.
    exposure = sig.map({1.0: leverage, 0.0: 1.0})
    res = run_exposure_strategy(underlying_returns, exposure, rf_daily, costs, label)
    res.meta.update({"window": window, "leverage_above": leverage,
                     "strategy": "leveraged_above_ma"})
    return res


def leverage_to_cash(prices: pd.Series, underlying_returns: pd.Series,
                     window: int, leverage: float, rf_daily=0.0,
                     costs: dict | None = None) -> StrategyResult:
    """Leverage the uptrend, then go fully to CASH below the MA.

    Above the MA: hold ``leverage``x S&P. Below the MA: hold cash (T-bills) — so
    the strategy completely sidesteps the big below-trend drawdowns, instead of
    riding them at 1x. exposure is ``leverage`` (above) or 0 (cash, below).
    """
    sig = lagged_signal(prices, window)
    exposure = sig.map({1.0: leverage, 0.0: 0.0})
    res = run_exposure_strategy(underlying_returns, exposure, rf_daily, costs,
                                name=f"Lev {leverage:g}x above->cash ({window}d)")
    res.meta.update({"window": window, "leverage_above": leverage,
                     "strategy": "leverage_to_cash"})
    return res


def three_tier_strategy(prices: pd.Series, underlying_returns: pd.Series,
                        leverage: float, slow_window: int = 200,
                        fast_window: int = 63, rf_daily=0.0,
                        costs: dict | None = None) -> StrategyResult:
    """A three-state "Leverage -> S&P -> Cash" rule using a fast (3-month) MA and
    a slow (200-day) MA:

        * above BOTH MAs           -> ``leverage``x  (strong uptrend)
        * above slow, below fast   -> 1x S&P         (mild pullback)
        * below the slow MA        -> cash           (real downtrend)

    Both signals are lagged one day (no look-ahead).
    """
    slow = lagged_signal(prices, slow_window)
    fast = lagged_signal(prices, fast_window)
    df = pd.concat([slow.rename("s"), fast.rename("f")], axis=1).dropna()
    exposure = pd.Series(1.0, index=df.index)          # default: 1x
    exposure[df["s"] == 0.0] = 0.0                      # below slow -> cash
    exposure[(df["s"] == 1.0) & (df["f"] == 1.0)] = leverage  # above both -> leverage
    res = run_exposure_strategy(underlying_returns, exposure, rf_daily, costs,
                                name=f"3-tier {leverage:g}x ({fast_window}/{slow_window}d)")
    res.meta.update({"slow_window": slow_window, "fast_window": fast_window,
                     "leverage_above": leverage, "strategy": "three_tier"})
    return res


def always_leveraged(underlying_returns: pd.Series, leverage: float,
                     rf_daily=0.0, costs: dict | None = None) -> StrategyResult:
    """A reference: hold ``leverage``x every single day (the naive HFEA-style bet).

    Useful to show what *constant* leverage does, versus only leveraging in bad
    trends. This is the purest demonstration of volatility decay.
    """
    exposure = pd.Series(leverage, index=underlying_returns.index)
    res = run_exposure_strategy(underlying_returns, exposure, rf_daily, costs,
                                name=f"Always {leverage:g}x")
    res.meta.update({"leverage_below": leverage, "strategy": "always_leveraged"})
    return res
