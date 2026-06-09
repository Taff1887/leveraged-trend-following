"""
test_core.py
============

Small, fast sanity tests for the engine. They lock in the properties that matter
most for an honest backtest:

* the volatility-decay arithmetic is exactly right,
* the trend signal has no look-ahead (it is lagged by one day),
* "leverage = 1x" reproduces buy-and-hold (no accidental drift),
* the headline metrics match hand-computed values on toy series,
* the Monte Carlo is reproducible from its seed.

Run with:   python -m pytest tests/ -q
       or:   python tests/test_core.py
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import returns as rt, signals as sg, backtest as bt, metrics as mx, \
    monte_carlo as mc, config


def _toy_prices(n=300, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-01", periods=n)
    rets = rng.normal(0.0004, 0.01, n)
    return pd.Series(100 * np.cumprod(1 + rets), index=idx)


# ---------------------------------------------------------------------------
def test_vol_decay_arithmetic():
    """+10% then -10% must give 1x=-1%, 2x=-4%, 3x=-9% (exactly)."""
    tbl = mc.vol_decay_table().set_index("leverage")["two_day_return"]
    assert abs(tbl["1x"] - (-0.01)) < 1e-12
    assert abs(tbl["2x"] - (-0.04)) < 1e-12
    assert abs(tbl["3x"] - (-0.09)) < 1e-12


def test_variance_drag_scales_with_square():
    """Variance drag must quadruple when leverage doubles."""
    d1 = mc.variance_drag(1.0, 0.2)
    d2 = mc.variance_drag(2.0, 0.2)
    assert abs(d2 / d1 - 4.0) < 1e-9


def test_signal_is_lagged_no_lookahead():
    """lagged_signal[t] must equal trend_signal[t-1] (one-day shift)."""
    px = _toy_prices()
    raw = sg.trend_signal(px, 50)
    lag = sg.lagged_signal(px, 50)
    # Align and compare on overlapping non-NaN region.
    shifted = raw.shift(1)
    both = pd.concat([lag, shifted], axis=1).dropna()
    assert (both.iloc[:, 0] == both.iloc[:, 1]).all()


def test_leverage_one_equals_buy_and_hold():
    """Leveraged-bad-market with L=1.0 must reproduce buy-and-hold exactly
    over the common (post-warmup) window."""
    px = _toy_prices()
    u = rt.simple_returns(px)
    bh = bt.buy_and_hold(u, costs=config.ZERO_COSTS)
    lev1 = bt.leveraged_bad_market(px, u, 50, 1.0, costs=config.ZERO_COSTS)
    common = bh.net_returns.index.intersection(lev1.net_returns.index)
    a = bh.net_returns.reindex(common)
    b = lev1.net_returns.reindex(common)
    assert np.allclose(a.values, b.values, atol=1e-12)


def test_cagr_on_known_series():
    """A series that exactly doubles over one trading year has CAGR ~ 100%."""
    n = config.TRADING_DAYS_PER_YEAR
    daily = 2.0 ** (1.0 / n) - 1.0
    idx = pd.bdate_range("2000-01-01", periods=n)
    r = pd.Series(daily, index=idx)
    assert abs(mx.cagr(r) - 1.0) < 1e-6


def test_max_drawdown_known():
    """Up 50% then down 50% from the peak => max drawdown = -50%."""
    idx = pd.bdate_range("2000-01-01", periods=3)
    # day1 +50%, day2 -50% (1.5 -> 0.75): drawdown from peak 1.5 is -50%.
    r = pd.Series([0.0, 0.5, -0.5], index=idx)
    assert abs(mx.max_drawdown(r) - (-0.5)) < 1e-12


def test_higher_leverage_deeper_drawdown():
    """On real-ish data, more leverage below the MA never makes the drawdown
    shallower (a core qualitative claim of the paper)."""
    px = _toy_prices(n=800, seed=3)
    u = rt.simple_returns(px)
    dds = []
    for L in [1.0, 2.0, 3.0]:
        res = bt.leveraged_bad_market(px, u, 100, L, costs=config.ZERO_COSTS)
        dds.append(mx.max_drawdown(res.net_returns))
    # drawdowns are negative; deeper = more negative => non-increasing
    assert dds[0] >= dds[1] >= dds[2]


def test_sortino_uses_total_obs_denominator():
    """Sortino downside deviation must average squared shortfalls over ALL
    observations (standard definition), not just the down days."""
    r = pd.Series([0.01, -0.02, 0.01, -0.03, 0.02],
                  index=pd.bdate_range("2000-01-01", periods=5))
    # Hand computation: mean excess = -0.002; downside dev = sqrt((0.02^2+0.03^2)/5)
    # = 0.0161245; annualized Sortino = (-0.002 / 0.0161245) * sqrt(252) ≈ -1.969.
    expected = (-0.002 / np.sqrt((0.02 ** 2 + 0.03 ** 2) / 5)) * np.sqrt(
        config.TRADING_DAYS_PER_YEAR)
    assert abs(mx.sortino_ratio(r) - expected) < 1e-6


def test_monthly_signal_single_month_lag():
    """Each trading month must use the decision from exactly ONE month earlier
    (Faber's rule) — not two months (the old double-lag bug)."""
    idx = pd.bdate_range("2015-01-01", "2018-12-31")
    rng = np.random.default_rng(7)
    px = pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.012, len(idx))),
                   index=idx)
    months = 5
    daily_sig = sg.monthly_trend_signal(px, months)
    # Independent month-end decisions, indexed by calendar month.
    m = px.resample("ME").last()
    sma = m.rolling(months, min_periods=months).mean()
    dec = (m > sma).astype(float); dec[sma.isna()] = np.nan
    dec_by_month = pd.Series(dec.values, index=dec.index.to_period("M"))
    checked = 0
    for p in pd.period_range("2016-06", "2018-06", freq="M"):
        days = daily_sig[daily_sig.index.to_period("M") == p].dropna()
        if len(days) == 0:
            continue
        expected = dec_by_month.get(p - 1, np.nan)  # decision from PREVIOUS month
        assert (days == expected).all(), f"month {p} mismatch"
        checked += 1
    assert checked > 10


def test_monte_carlo_reproducible():
    """Same seed must give identical simulated returns."""
    rng1 = np.random.default_rng(123)
    rng2 = np.random.default_rng(123)
    a = mc.simulate_base_returns(0.08, 0.2, 252, 50, rng1)
    b = mc.simulate_base_returns(0.08, 0.2, 252, 50, rng2)
    assert np.array_equal(a, b)


def test_mc_prob_beat_1x_self_is_zero():
    """1x can never strictly beat 1x on identical draws => prob_beat_1x == 0."""
    rows = mc.simulate_cell(0.08, 0.2, [1.0], [5], n_paths=200, seed=1)
    assert rows[0]["prob_beat_1x"] == 0.0


if __name__ == "__main__":
    # Allow running without pytest.
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} tests passed.")
    sys.exit(1 if failed else 0)
