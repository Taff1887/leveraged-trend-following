"""
run_all.py
==========

The master pipeline. Running this one file reproduces EVERYTHING in the project:
all result tables (-> results/), all charts (-> charts/), and a headline JSON
(results/headline_results.json) that the research paper and README read from.

It walks through the same parts as the paper:

    Part 1  Buy-and-hold baseline
    Part 2  Moving-average-to-cash baseline (Faber-style)
    Part 3  The leveraged bad-market strategy
    Part 4  Parameter sweep (window x leverage x cost) + heatmaps
    Part 5  Period & episode analysis
    Part 6  ETF implementation tests (synthetic vs real leveraged ETFs)
    Part 7  Monte Carlo: volatility decay & optimal leverage

Usage
-----
    python run_all.py                 # full run (uses cached data; downloads if missing)
    python run_all.py --fast          # smaller Monte Carlo for a quick run
    python run_all.py --mc-paths 10000

Everything is reproducible: data is cached in data/raw, and the Monte Carlo uses
a fixed seed from config.
"""

from __future__ import annotations

import argparse
import json
import warnings

import matplotlib
matplotlib.use("Agg")  # headless: just write PNGs, never open a window
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from src import config
from src import data_loader as dl
from src import data_cleaning as dc
from src import returns as rt
from src import backtest as bt
from src import metrics as mx
from src import sweep as sw
from src import plots as pl
from src import monte_carlo as mc
from src import etf_tests as et


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def save_table(df: pd.DataFrame, name: str, index: bool = False) -> None:
    """Save a DataFrame to results/ as CSV and print a one-line confirmation."""
    path = config.RESULTS_DIR / name
    df.to_csv(path, index=index)
    print(f"    saved table -> results/{name}  ({len(df)} rows)")


def save_chart(fig, name: str) -> None:
    pl.save_fig(fig, name)
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"    saved chart -> charts/{name}")


def align_common(returns_dict: dict) -> dict:
    """Restrict several return series to their COMMON date range (fair compare)."""
    common = None
    for r in returns_dict.values():
        idx = r.dropna().index
        common = idx if common is None else common.intersection(idx)
    return {k: v.reindex(common).dropna() for k, v in returns_dict.items()}


def r3(x):
    """Round floats for the JSON summary; pass through everything else."""
    try:
        return round(float(x), 4)
    except (TypeError, ValueError):
        return x


HEADLINE = {}  # filled in as we go, dumped to JSON at the end


# ===========================================================================
# DATA
# ===========================================================================
def load_and_clean():
    print("[data] loading + cleaning ...")
    tickers = ["^SP500TR", "SPY", "^GSPC", "^IRX",
               "SSO", "UPRO", "SPXL", "VOO", "IVV", "SPLG"]
    raw = dl.load_universe(tickers)
    clean, reports = dc.clean_universe(raw)

    summary = dc.build_data_summary(clean, reports)
    save_table(summary, "data_summary.csv")

    # Canonical underlying (true total return) + risk-free daily series.
    underlying, u_ticker, u_source = dl.get_underlying_total_return()
    underlying, _ = dc.clean_level_series(underlying)
    u_rets = rt.simple_returns(underlying)
    rf_daily = dl.get_risk_free_daily(u_rets.index)

    HEADLINE["data"] = {
        "underlying_ticker": u_ticker,
        "underlying_source": u_source,
        "underlying_start": str(underlying.index.min().date()),
        "underlying_end": str(underlying.index.max().date()),
        "n_days": int(len(u_rets)),
        "years": r3(mx.n_years(u_rets)),
        "risk_free_source": "Yahoo ^IRX (13-week T-bill)" if len(rf_daily) else "fallback constant",
    }
    print(f"    underlying = {u_ticker} ({u_source})")
    print(f"    {underlying.index.min().date()} -> {underlying.index.max().date()}, "
          f"{len(u_rets)} days")
    return clean, underlying, u_rets, rf_daily


# ===========================================================================
# PART 1: buy-and-hold
# ===========================================================================
def part1_buy_and_hold(clean, underlying, u_rets, rf_daily):
    print("[part 1] buy-and-hold baseline ...")
    bh = bt.buy_and_hold(u_rets, rf_daily=rf_daily, name="Buy & Hold S&P 500 TR")
    s = bh.summary(rf_daily=rf_daily)
    tbl = mx.summary_frame([s])
    save_table(tbl, "part1_buyhold_metrics.csv")
    HEADLINE["part1_buy_and_hold"] = {k: r3(v) for k, v in s.items()
                                      if k not in ("start", "end")}

    # Chart: cumulative total return (log scale).
    fig = pl.plot_cumulative({"S&P 500 Total Return": underlying},
                             "S&P 500 Total Return — Growth of $1",
                             "01_sp500_cumulative.png", log=True)
    save_chart(fig, "01_sp500_cumulative.png")

    # Long-history context using the price-only ^GSPC index (1927+).
    if "^GSPC" in clean:
        fig = pl.plot_cumulative({"S&P 500 price index (^GSPC, no dividends)": clean["^GSPC"]},
                                 "S&P 500 price index since 1927 (price only — context)",
                                 "01_sp500_long_context.png", log=True)
        save_chart(fig, "01_sp500_long_context.png")
    return bh


# ===========================================================================
# PART 2: moving-average-to-cash baseline
# ===========================================================================
def part2_ma_to_cash(underlying, u_rets, rf_daily, bh):
    print("[part 2] moving-average-to-cash baseline ...")
    rows = []
    results = {}
    for w in config.MA_WINDOWS:
        res = bt.ma_to_cash(underlying, u_rets, w, rf_daily=rf_daily,
                            costs=config.ZERO_COSTS)
        results[w] = res
        s = res.summary(rf_daily=rf_daily)
        s["window"] = w
        rows.append(s)
    # Buy-and-hold row for reference.
    bh_s = bh.summary(rf_daily=rf_daily)
    bh_s["window"] = "buy&hold"
    rows.append(bh_s)
    tbl = mx.summary_frame(rows)
    save_table(tbl, "part2_ma_timing_metrics.csv")

    # Pick the 200-day rule as the canonical baseline for charts/headline.
    ma200 = results[200]
    HEADLINE["part2_ma_to_cash_200d"] = {
        k: r3(v) for k, v in ma200.summary(rf_daily=rf_daily).items()
        if k not in ("start", "end")}

    # Signal chart.
    fig = pl.plot_ma_signal(underlying, 200, "02_ma_signal_200d.png")
    save_chart(fig, "02_ma_signal_200d.png")

    # Equity / drawdown / rolling comparisons: buy&hold vs MA200->cash.
    comp = align_common({"Buy & Hold": bh.net_returns,
                         "MA200 → Cash": ma200.net_returns})
    eq = {k: rt.cumulative_index(v) for k, v in comp.items()}
    colors = {"Buy & Hold": config.COLORS["buy_hold"], "MA200 → Cash": config.COLORS["ma_cash"]}

    fig = pl.plot_equity_comparison(eq, "Buy & Hold vs MA200 → Cash",
                                    "02_equity_buyhold_vs_timing.png", colors=colors)
    save_chart(fig, "02_equity_buyhold_vs_timing.png")
    fig = pl.plot_drawdowns(comp, "Drawdowns: Buy & Hold vs MA200 → Cash",
                            "02_drawdowns_timing.png", colors=colors)
    save_chart(fig, "02_drawdowns_timing.png")
    fig = pl.plot_rolling_returns(comp, 3, "Rolling 3-year annualized return",
                                  "02_rolling3y_returns.png", colors=colors)
    save_chart(fig, "02_rolling3y_returns.png")
    fig = pl.plot_rolling_sharpe(comp, 3, "Rolling 3-year Sharpe ratio",
                                 "02_rolling_sharpe.png", colors=colors)
    save_chart(fig, "02_rolling_sharpe.png")
    return results


# ===========================================================================
# PART 3: leveraged bad-market strategy
# ===========================================================================
def part3_leveraged(underlying, u_rets, rf_daily, bh, ma_results):
    print("[part 3] leveraged bad-market strategy ...")
    # Headline focus: 200-day window across all leverage levels (gross).
    rows = []
    lev_results = {}
    for L in config.LEVERAGE_LEVELS:
        res = bt.leveraged_bad_market(underlying, u_rets, 200, L,
                                      rf_daily=rf_daily, costs=config.ZERO_COSTS)
        lev_results[L] = res
        s = res.summary(rf_daily=rf_daily)
        s["leverage"] = L
        s["window"] = 200
        rows.append(s)
    tbl = mx.summary_frame(rows)
    save_table(tbl, "part3_leveraged_200d_metrics.csv")
    HEADLINE["part3_leveraged_200d"] = {
        f"{L:g}x": {k: r3(v) for k, v in lev_results[L].summary(rf_daily=rf_daily).items()
                    if k in ("cagr", "volatility", "sharpe", "max_drawdown", "calmar")}
        for L in config.LEVERAGE_LEVELS}

    # Reference: always-leveraged (constant) to show pure volatility decay.
    always = {L: bt.always_leveraged(u_rets, L, rf_daily=rf_daily,
                                     costs=config.ZERO_COSTS)
              for L in [1.0, 2.0, 3.0]}

    # Equity comparison: B&H vs MA200->cash vs leveraged (1.5x, 2x, 3x below MA).
    comp_returns = {
        "Buy & Hold (1x)": bh.net_returns,
        "MA200 → Cash": ma_results[200].net_returns,
        "Lev 1.5x below MA": lev_results[1.5].net_returns,
        "Lev 2x below MA": lev_results[2.0].net_returns,
        "Lev 3x below MA": lev_results[3.0].net_returns,
    }
    comp_returns = align_common(comp_returns)
    eq = {k: rt.cumulative_index(v) for k, v in comp_returns.items()}
    fig = pl.plot_equity_comparison(eq, "Buy & Hold vs MA→Cash vs Leveraged Bad-Market (200-day)",
                                    "03_equity_leverage_levels_200d.png")
    save_chart(fig, "03_equity_leverage_levels_200d.png")
    fig = pl.plot_drawdowns(comp_returns, "Drawdowns: leverage deepens the holes (200-day)",
                            "03_drawdowns_leverage.png")
    save_chart(fig, "03_drawdowns_leverage.png")

    # Always-leveraged equity (pure decay illustration).
    always_eq = {f"Always {L:g}x": always[L].equity for L in [1.0, 2.0, 3.0]}
    fig = pl.plot_equity_comparison(always_eq,
                                    "Constant daily leverage on the S&P 500 (volatility decay)",
                                    "03_always_leveraged.png")
    save_chart(fig, "03_always_leveraged.png")
    return lev_results


# ===========================================================================
# PART 4: parameter sweep + heatmaps
# ===========================================================================
def part4_sweep(underlying, u_rets, rf_daily):
    print("[part 4] parameter sweep ...")
    cost_scenarios = {"gross (0 cost)": config.ZERO_COSTS,
                      "net (realistic)": config.DEFAULT_COSTS}
    sweep = sw.run_parameter_sweep(underlying, u_rets, rf_daily=rf_daily,
                                   cost_scenarios=cost_scenarios)
    save_table(sweep, "part4_parameter_sweep.csv")

    # Which leveraged strategies beat buy-and-hold, in each cost scenario?
    for label, tag in [("gross (0 cost)", "gross"), ("net (realistic)", "net")]:
        beats = sw.beats_baseline(sweep, label)
        save_table(beats[["name", "window", "leverage", "cagr", "sharpe",
                          "max_drawdown", "calmar", "beats_cagr", "beats_sharpe",
                          "beats_calmar", "beats_maxdd", "beats_all"]],
                   f"part4_beats_baseline_{tag}.csv")
        HEADLINE[f"part4_beats_all_count_{tag}"] = int(beats["beats_all"].sum())
        HEADLINE[f"part4_beats_cagr_count_{tag}"] = int(beats["beats_cagr"].sum())
        HEADLINE[f"part4_beats_sharpe_count_{tag}"] = int(beats["beats_sharpe"].sum())

    # Heatmaps (window x leverage) for both cost scenarios.
    for label, tag in [("gross (0 cost)", "gross"), ("net (realistic)", "net")]:
        for value, fmt, cmap, center, cbar in [
            ("cagr", ".1%", "RdYlGn", None, "CAGR"),
            ("sharpe", ".2f", "RdYlGn", None, "Sharpe"),
            ("max_drawdown", ".0%", "RdYlGn", None, "Max drawdown"),
            ("calmar", ".2f", "RdYlGn", None, "Calmar"),
        ]:
            mat = sw.heatmap_matrix(sweep, value, label)
            mat.index = [config.MA_WINDOW_LABELS.get(w, str(w)) for w in mat.index]
            fig = pl.plot_heatmap(mat, f"{cbar} by MA window & leverage — {label}",
                                  f"04_heatmap_{value}_{tag}.png", fmt=fmt, cmap=cmap,
                                  center=center, xlabel="Leverage when below MA",
                                  ylabel="MA window", cbar_label=cbar)
            save_chart(fig, f"04_heatmap_{value}_{tag}.png")

    # Find the single best GENUINELY leveraged config (>1x) by Sharpe and by
    # Calmar, net of costs. (Leverage = 1.0 just reproduces buy-and-hold.)
    net_lev = sweep[(sweep["cost_scenario"] == "net (realistic)")
                    & (sweep["strategy"] == "leveraged_bad_market")
                    & (sweep["leverage"] > 1.0)]
    best_sharpe = net_lev.loc[net_lev["sharpe"].idxmax()]
    best_calmar = net_lev.loc[net_lev["calmar"].idxmax()]
    HEADLINE["part4_best_net"] = {
        "by_sharpe": {"name": best_sharpe["name"], "sharpe": r3(best_sharpe["sharpe"]),
                      "cagr": r3(best_sharpe["cagr"]), "max_dd": r3(best_sharpe["max_drawdown"])},
        "by_calmar": {"name": best_calmar["name"], "calmar": r3(best_calmar["calmar"]),
                      "cagr": r3(best_calmar["cagr"]), "max_dd": r3(best_calmar["max_drawdown"])},
    }
    return sweep


# ===========================================================================
# PART 5: period & episode analysis
# ===========================================================================
def part5_periods(clean, underlying, u_rets, rf_daily, bh, ma_results, lev_results):
    print("[part 5] period & episode analysis ...")
    # Headline 3 strategies (total-return based, 1988+).
    strategies = {
        "Buy & Hold": bh.net_returns,
        "MA200 → Cash": ma_results[200].net_returns,
        "Lev 2x below MA200": lev_results[2.0].net_returns,
    }
    period_tbl = sw.evaluate_periods(strategies, config.PERIODS, rf_daily=rf_daily)
    save_table(period_tbl, "part5_period_analysis_TR.csv")

    helped = sw.did_leverage_help(period_tbl, "Buy & Hold",
                                  "Lev 2x below MA200", metric="total_return")
    save_table(helped, "part5_leverage_helped.csv")
    HEADLINE["part5_periods_leverage_helped_frac"] = r3(helped["leverage_helped"].mean())

    # Episodes: use the long price-only ^GSPC so 1929 / 1987 are covered.
    if "^GSPC" in clean:
        g = clean["^GSPC"]
        g_rets = rt.simple_returns(g)
        bh_g = bt.buy_and_hold(g_rets, costs=config.ZERO_COSTS)
        ma_g = bt.ma_to_cash(g, g_rets, 200, costs=config.ZERO_COSTS)
        lev2_g = bt.leveraged_bad_market(g, g_rets, 200, 2.0, costs=config.ZERO_COSTS)
        lev3_g = bt.leveraged_bad_market(g, g_rets, 200, 3.0, costs=config.ZERO_COSTS)
        ep_strats = {
            "Buy & Hold (price)": bh_g.net_returns,
            "MA200 → Cash (price)": ma_g.net_returns,
            "Lev 2x below MA (price)": lev2_g.net_returns,
            "Lev 3x below MA (price)": lev3_g.net_returns,
        }
        ep_tbl = sw.evaluate_periods(ep_strats, config.EPISODES)
        save_table(ep_tbl, "part5_episode_analysis_priceonly.csv")
    return period_tbl


# ===========================================================================
# PART 6: ETF implementation tests
# ===========================================================================
def part6_etf(clean, underlying, u_rets, rf_daily):
    print("[part 6] ETF implementation tests ...")
    # Compare synthetic leverage to each real leveraged ETF over its own history.
    rows = []
    for etf_ticker in ["SSO", "UPRO", "SPXL"]:
        if etf_ticker not in clean:
            continue
        L = config.TICKERS[etf_ticker]["leverage"]
        exp = config.TICKERS[etf_ticker]["expense"]
        etf_rets = rt.simple_returns(clean[etf_ticker])
        cmp = et.compare_synthetic_vs_real(u_rets, etf_rets, L, rf_daily=rf_daily,
                                           expense_annual=exp)
        rows.append({
            "etf": etf_ticker, "leverage": L,
            "start": cmp["start"].date(), "end": cmp["end"].date(),
            "n_days": cmp["n_days"],
            "realized_beta": cmp["realized_beta"],
            "tracking_error_ann": cmp["tracking_error_ann"],
            "etf_cagr": cmp["etf_cagr"],
            "synthetic_gross_cagr": cmp["synthetic_gross_cagr"],
            "synthetic_costed_cagr": cmp["synthetic_costed_cagr"],
            "gap_gross_minus_etf": cmp["gap_gross_minus_etf"],
            "gap_costed_minus_etf": cmp["gap_costed_minus_etf"],
        })
        # Chart for SSO (2x) and the first 3x ETF we see.
        if etf_ticker in ("SSO", "UPRO"):
            fig = pl.plot_synthetic_vs_real(
                cmp["curves"], f"Synthetic {L:g}x vs real {etf_ticker} ({L:g}x)",
                f"06_etf_synth_vs_real_{etf_ticker}.png")
            save_chart(fig, f"06_etf_synth_vs_real_{etf_ticker}.png")
    etf_tbl = pd.DataFrame(rows)
    if len(etf_tbl):
        save_table(etf_tbl, "part6_etf_synth_vs_real.csv")
        HEADLINE["part6_etf_tracking"] = etf_tbl.assign(
            tracking_error_ann=etf_tbl["tracking_error_ann"].round(4),
            gap_costed_minus_etf=etf_tbl["gap_costed_minus_etf"].round(4),
            realized_beta=etf_tbl["realized_beta"].round(3),
        )[["etf", "leverage", "realized_beta", "tracking_error_ann",
           "gap_costed_minus_etf"]].to_dict("records")

    # Run the strategy with REAL ETF returns below the MA, vs the synthetic version.
    strat_rows = []
    for etf_ticker in ["SSO", "UPRO", "SPXL"]:
        if etf_ticker not in clean:
            continue
        L = config.TICKERS[etf_ticker]["leverage"]
        etf_rets = rt.simple_returns(clean[etf_ticker])
        out = et.strategy_with_real_etf(underlying, u_rets, etf_rets, 200, L,
                                        rf_daily=rf_daily)
        rsum = out["real"]["summary"]
        ssum = out["synthetic"]["summary"]
        strat_rows.append({
            "etf": etf_ticker, "leverage": L, "window": 200,
            "real_cagr": rsum["cagr"], "synthetic_cagr": ssum["cagr"],
            "real_sharpe": rsum["sharpe"], "synthetic_sharpe": ssum["sharpe"],
            "real_max_dd": rsum["max_drawdown"], "synthetic_max_dd": ssum["max_drawdown"],
        })
    if strat_rows:
        save_table(pd.DataFrame(strat_rows), "part6_etf_strategy.csv")


# ===========================================================================
# PART 7: Monte Carlo
# ===========================================================================
def part7_monte_carlo(u_rets, mc_paths):
    print(f"[part 7] Monte Carlo grid (n_paths={mc_paths}) ...")
    # The volatility-decay teaching table + chart.
    vd = mc.vol_decay_table()
    save_table(vd, "part7_vol_decay_table.csv")
    fig = pl.plot_vol_decay_example("volatility_decay_example.png")
    save_chart(fig, "volatility_decay_example.png")

    # Full grid.
    grid = mc.run_grid(n_paths=mc_paths, verbose=True)
    save_table(grid, "part7_monte_carlo_grid.csv")

    H = 10  # headline horizon for the heatmaps
    # Optimal leverage by drift & vol (maximise median terminal wealth).
    opt = mc.optimal_leverage_grid(grid, H, objective="median_terminal")
    opt.index = [f"{v:.0%}" for v in opt.index]
    opt.columns = [f"{d:.0%}" for d in opt.columns]
    fig = pl.plot_heatmap(opt, f"Optimal leverage (max median wealth, {H}-yr)",
                          "07_mc_optimal_leverage.png", fmt=".2g", cmap="viridis",
                          xlabel="Annual drift", ylabel="Annual volatility",
                          cbar_label="Best leverage")
    save_chart(fig, "07_mc_optimal_leverage.png")

    # Probability 2x / 3x beat 1x.
    for L in [2.0, 3.0]:
        m = mc.prob_beat_1x_grid(grid, H, L)
        m.index = [f"{v:.0%}" for v in m.index]
        m.columns = [f"{d:.0%}" for d in m.columns]
        fig = pl.plot_heatmap(m, f"P( {L:g}x beats 1x ) — {H}-yr horizon",
                              f"07_mc_prob_{int(L)}x_beats_1x.png", fmt=".0%",
                              cmap="RdYlGn", center=0.5, xlabel="Annual drift",
                              ylabel="Annual volatility", cbar_label="Probability")
        save_chart(fig, f"07_mc_prob_{int(L)}x_beats_1x.png")

    # Median terminal wealth for 2x and risk of >50% drawdown for 3x.
    m = mc.metric_grid(grid, H, 2.0, "median_terminal")
    m.index = [f"{v:.0%}" for v in m.index]; m.columns = [f"{d:.0%}" for d in m.columns]
    fig = pl.plot_heatmap(m, f"Median terminal wealth, 2x ({H}-yr, start=$1)",
                          "07_mc_median_terminal_2x.png", fmt=".2f", cmap="RdYlGn",
                          center=1.0, xlabel="Annual drift", ylabel="Annual volatility",
                          cbar_label="Median $ per $1")
    save_chart(fig, "07_mc_median_terminal_2x.png")

    m = mc.metric_grid(grid, H, 3.0, "prob_dd_gt_50")
    m.index = [f"{v:.0%}" for v in m.index]; m.columns = [f"{d:.0%}" for d in m.columns]
    fig = pl.plot_heatmap(m, f"P( drawdown > 50% ), 3x ({H}-yr)",
                          "07_mc_prob_dd50_3x.png", fmt=".0%", cmap="RdYlGn_r",
                          center=0.5, xlabel="Annual drift", ylabel="Annual volatility",
                          cbar_label="Probability")
    save_chart(fig, "07_mc_prob_dd50_3x.png")

    # Expected CAGR by leverage at an S&P-like point (drift~7%, vol~16%), 10k paths.
    sp_drift = round(mx.cagr(u_rets), 2) if len(u_rets) else 0.08
    sp_vol = round(mx.annual_volatility(u_rets), 2) if len(u_rets) else 0.16
    focus = mc.run_grid(drifts=[sp_drift], vols=[sp_vol], horizons_years=[10],
                        n_paths=max(mc_paths, 10000), verbose=False)
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(focus["leverage"], focus["median_cagr"] * 100, marker="o", label="median CAGR")
    ax.plot(focus["leverage"], focus["prob_beat_1x"] * 100, marker="s",
            label="P(beat 1x) %")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("Leverage"); ax.set_ylabel("Percent")
    ax.set_title(f"S&P-like point (drift={sp_drift:.0%}, vol={sp_vol:.0%}, 10-yr): "
                 f"CAGR & P(beat 1x) vs leverage")
    ax.legend()
    save_chart(fig, "07_mc_cagr_by_leverage.png")

    HEADLINE["part7_sp_like_point"] = {
        "drift": sp_drift, "vol": sp_vol,
        "median_cagr_by_leverage": {f"{row.leverage:g}x": r3(row.median_cagr)
                                    for row in focus.itertuples()},
        "prob_beat_1x_by_leverage": {f"{row.leverage:g}x": r3(row.prob_beat_1x)
                                     for row in focus.itertuples()},
    }
    # The leverage that maximises median terminal wealth at the S&P-like point.
    best_row = focus.loc[focus["median_terminal"].idxmax()]
    HEADLINE["part7_sp_like_optimal_leverage"] = r3(best_row["leverage"])
    return grid


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true",
                        help="use a smaller Monte Carlo grid for a quick run")
    parser.add_argument("--mc-paths", type=int, default=None,
                        help="number of Monte Carlo paths (overrides default)")
    args = parser.parse_args()

    mc_paths = args.mc_paths or (config.MC_N_PATHS_FAST if args.fast else 4000)

    print("=" * 70)
    print(" Leveraged Trend-Following — full pipeline")
    print("=" * 70)

    clean, underlying, u_rets, rf_daily = load_and_clean()
    bh = part1_buy_and_hold(clean, underlying, u_rets, rf_daily)
    ma_results = part2_ma_to_cash(underlying, u_rets, rf_daily, bh)
    lev_results = part3_leveraged(underlying, u_rets, rf_daily, bh, ma_results)
    sweep = part4_sweep(underlying, u_rets, rf_daily)
    part5_periods(clean, underlying, u_rets, rf_daily, bh, ma_results, lev_results)
    part6_etf(clean, underlying, u_rets, rf_daily)
    part7_monte_carlo(u_rets, mc_paths)

    # Dump headline numbers for the paper / README.
    out = config.RESULTS_DIR / "headline_results.json"
    with open(out, "w") as f:
        json.dump(HEADLINE, f, indent=2, default=str)
    print(f"\n[done] headline results -> results/headline_results.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
