"""
build_notebooks.py
==================

Generates the eight teaching notebooks in notebooks/ from a single, version-
controlled source. We build them programmatically (with nbformat) so they are
ALWAYS valid JSON, use the real ``src`` API correctly, and stay consistent with
each other. Re-run this any time the API or narrative changes:

    python build_notebooks.py

The notebooks are designed to be read IN ORDER, from the simplest idea
(load some prices) to the most advanced (Monte Carlo of volatility decay). Each
one is short, heavily narrated, and runnable in seconds (the Monte Carlo
notebook uses a small, fast grid; the full grid lives in run_all.py).
"""

from __future__ import annotations

import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

from src import config

NB_DIR = config.PROJECT_ROOT / "notebooks"
NB_DIR.mkdir(exist_ok=True)

# Standard setup cell prepended to every notebook so `from src import ...` works
# and charts render inline regardless of where Jupyter is launched.
SETUP = """\
# --- standard setup (run me first) ---
import sys, os
# Make the project root importable so `from src import ...` works from notebooks/.
sys.path.insert(0, os.path.abspath(".."))
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
%matplotlib inline
pd.set_option("display.float_format", lambda x: f"{x:,.4f}")
print("Setup complete. Project root:", os.path.abspath(".."))"""


def build(filename: str, cells: list) -> None:
    nb = new_notebook()
    nb.cells = cells
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python",
                       "name": "python3"},
        "language_info": {"name": "python"},
    }
    path = NB_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)
    print(f"  wrote notebooks/{filename}  ({len(cells)} cells)")


def md(text):
    return new_markdown_cell(text)


def code(src):
    return new_code_cell(src)


# ===========================================================================
# 01 — basic S&P 500 data
# ===========================================================================
def nb01():
    cells = [
        md("# 01 — Basic S&P 500 Data\n\n"
           "**Goal of this notebook:** load the longest, cleanest S&P 500 "
           "*total-return* data we can get, look at it, and plot the growth of "
           "$1. Nothing fancy yet — we are just getting comfortable with the data.\n\n"
           "**Key idea — total return vs price:** the *price* index (like the "
           "number you see on TV) ignores dividends. The *total-return* index "
           "reinvests dividends, so it reflects what a real buy-and-hold investor "
           "actually earns. We use total return everywhere we can."),
        code(SETUP),
        md("## Load the data\n\n"
           "`data_loader.get_underlying_total_return()` tries, in order:\n"
           "1. `^SP500TR` — the true daily S&P 500 Total Return index (from 1988),\n"
           "2. `SPY` adjusted close — an investable proxy (from 1993),\n"
           "3. a clearly-labelled **synthetic** series (only if you are offline).\n\n"
           "Data is cached in `data/raw`, so this is instant after the first run."),
        code("from src import data_loader as dl, data_cleaning as dc, returns as rt\n"
             "from src import metrics as mx, plots as pl\n\n"
             "underlying, ticker, source = dl.get_underlying_total_return()\n"
             "print('Series :', ticker)\n"
             "print('Source :', source)\n"
             "print('Range  :', underlying.index.min().date(), '->', underlying.index.max().date())\n"
             "print('Points :', len(underlying))"),
        md("## Clean it and build the data-summary table\n\n"
           "Cleaning = sort dates, drop duplicates, trim missing values, and "
           "*report* every decision. We also load the wider universe (proxies, "
           "leveraged ETFs, T-bills) just to summarise what data exists."),
        code("tickers = ['^SP500TR','SPY','^GSPC','^IRX','SSO','UPRO','SPXL','VOO','IVV','SPLG']\n"
             "raw = dl.load_universe(tickers)\n"
             "clean, reports = dc.clean_universe(raw)\n"
             "summary = dc.build_data_summary(clean, reports)\n"
             "summary[['ticker','role','leverage','first_date','last_date',"
             "'n_observations','kind','source']]"),
        md("Notice the different histories: the price-only `^GSPC` reaches back to "
           "1927, the total-return `^SP500TR` to 1988, and the leveraged ETFs "
           "(SSO 2006, SPXL 2008, UPRO 2009) are much younger. This is why we lean "
           "on the synthetic-leverage backtest for long history and use the real "
           "ETFs as a reality check (notebook 06)."),
        md("## Daily returns and the growth of $1"),
        code("u = rt.simple_returns(underlying)\n"
             "print('First few daily returns:')\n"
             "print(u.head())\n\n"
             "fig = pl.plot_cumulative({'S&P 500 Total Return': underlying},\n"
             "                         'S&P 500 Total Return — Growth of $1',\n"
             "                         '01_sp500_cumulative.png', log=True)\n"
             "plt.show()"),
        md("**Why a log scale?** On a log axis, a straight line means a *constant "
           "percentage* growth rate. Equal vertical distances are equal multiples "
           "(e.g. doubling), which is the honest way to look at decades of "
           "compounding. We will use log scales for almost every equity curve.\n\n"
           "➡️ **Next:** notebook 02 turns this series into proper performance "
           "statistics (CAGR, volatility, Sharpe, drawdown)."),
    ]
    build("01_basic_sp500_data.ipynb", cells)


# ===========================================================================
# 02 — simple buy and hold
# ===========================================================================
def nb02():
    cells = [
        md("# 02 — Simple Buy-and-Hold\n\n"
           "**Goal:** measure the plain buy-and-hold S&P 500 strategy properly. "
           "Every later strategy is judged against this baseline, so we need to "
           "know exactly what 'just hold the index' delivers.\n\n"
           "We compute, and explain, each statistic:\n"
           "- **CAGR** — the constant yearly growth rate that links start to end.\n"
           "- **Volatility** — annualized standard deviation of daily returns.\n"
           "- **Sharpe** — excess return per unit of total volatility.\n"
           "- **Sortino** — like Sharpe but only penalizes *downside* moves.\n"
           "- **Max drawdown** — worst peak-to-trough fall.\n"
           "- **Calmar** — CAGR ÷ |max drawdown| (return per unit of pain)."),
        code(SETUP),
        code("from src import data_loader as dl, returns as rt, backtest as bt\n"
             "from src import metrics as mx, plots as pl\n\n"
             "underlying, ticker, source = dl.get_underlying_total_return()\n"
             "u = rt.simple_returns(underlying)\n"
             "rf = dl.get_risk_free_daily(u.index)   # daily T-bill return for Sharpe\n"
             "print('Loaded', ticker, len(u), 'daily returns')"),
        md("## Run buy-and-hold and summarise it\n\n"
           "The backtester treats buy-and-hold as 'exposure = 1.0 every day'. The "
           "`summary()` method returns every statistic in one dict."),
        code("bh = bt.buy_and_hold(u, rf_daily=rf, name='Buy & Hold S&P 500 TR')\n"
             "s = bh.summary(rf_daily=rf)\n"
             "import pandas as pd\n"
             "pd.Series(s)"),
        md("## What the numbers say\n\n"
           "Read off the CAGR, volatility, Sharpe and — most importantly — the "
           "**maximum drawdown**. Buy-and-hold compounds nicely over decades, but "
           "it also lived through losing more than half its value (2000–02 and "
           "2007–09). That pain is the thing every 'improvement' in this project "
           "is trying to reduce."),
        code("metrics_we_care_about = ['cagr','volatility','sharpe','sortino',\n"
             "    'max_drawdown','calmar','worst_day','best_day','worst_month',\n"
             "    'best_month','pct_positive_days','pct_positive_months']\n"
             "pd.Series({k: s[k] for k in metrics_we_care_about})"),
        md("## The drawdown chart\n\n"
           "Drawdown = how far below the previous high-water mark we are, at every "
           "point in time. It is the single most intuitive picture of risk."),
        code("fig = pl.plot_drawdowns({'Buy & Hold': bh.net_returns},\n"
             "    'Buy-and-hold drawdowns (underwater plot)', '02_bh_drawdown.png',\n"
             "    colors={'Buy & Hold': '#1f77b4'})\n"
             "plt.show()"),
        md("➡️ **Next:** notebook 03 adds the classic Faber-style moving-average "
           "rule that tries to dodge the worst of those drawdowns by moving to cash."),
    ]
    build("02_simple_buy_and_hold.ipynb", cells)


# ===========================================================================
# 03 — moving average timing
# ===========================================================================
def nb03():
    cells = [
        md("# 03 — Moving-Average Timing (the Faber baseline)\n\n"
           "**Goal:** replicate the classic trend rule from Mebane Faber's "
           "tactical-allocation work:\n\n"
           "> If the index is **above** its moving average → hold the S&P 500.\n"
           "> If the index is **below** its moving average → move to **cash**.\n\n"
           "The moving average is just the average price over the last *N* days. "
           "Being above it is a simple definition of 'in an uptrend'.\n\n"
           "**No look-ahead:** we decide today's position using *yesterday's* "
           "signal. The `lagged_signal` function shifts the signal by one day so "
           "we never trade on information we could not have had."),
        code(SETUP),
        code("from src import data_loader as dl, returns as rt, signals as sg\n"
             "from src import backtest as bt, metrics as mx, plots as pl, config\n\n"
             "underlying, ticker, _ = dl.get_underlying_total_return()\n"
             "u = rt.simple_returns(underlying)\n"
             "rf = dl.get_risk_free_daily(u.index)"),
        md("## The signal, drawn\n\n"
           "Shaded red = the index is **below** its 200-day average. Those are the "
           "periods the classic rule sits in cash — and the periods our later "
           "strategy will try to *leverage* instead."),
        code("fig = pl.plot_ma_signal(underlying, 200, '02_ma_signal_200d.png')\n"
             "plt.show()"),
        md("## Test several moving-average windows\n\n"
           "Faber's original rule is monthly (a 10-month average). On daily data, "
           "the rough equivalents are ~200–252 days. We test a range and compare "
           "each to buy-and-hold. Cash earns the real T-bill rate."),
        code("rows = []\n"
             "for w in config.MA_WINDOWS:\n"
             "    res = bt.ma_to_cash(underlying, u, w, rf_daily=rf, costs=config.ZERO_COSTS)\n"
             "    srow = res.summary(rf_daily=rf); srow['window'] = w\n"
             "    rows.append(srow)\n"
             "bh = bt.buy_and_hold(u, rf_daily=rf); bhrow = bh.summary(rf_daily=rf)\n"
             "bhrow['window'] = 'buy&hold'; rows.append(bhrow)\n"
             "tbl = mx.summary_frame(rows)\n"
             "tbl[['window','cagr','volatility','sharpe','max_drawdown','calmar','n_switches']]"),
        md("**What to notice:** the timing rule usually gives up a little CAGR but "
           "*dramatically* cuts volatility and drawdown, so its Sharpe and Calmar "
           "are higher. That is the whole appeal of trend-following: similar "
           "returns, far less pain. The 200-day window is a sensible, robust "
           "middle-of-the-road choice."),
        md("## Buy-and-hold vs MA200 → cash"),
        code("ma200 = bt.ma_to_cash(underlying, u, 200, rf_daily=rf, costs=config.ZERO_COSTS)\n"
             "comp = {'Buy & Hold': bh.net_returns, 'MA200 -> Cash': ma200.net_returns}\n"
             "# align to the common window so the comparison is fair\n"
             "common = bh.net_returns.index.intersection(ma200.net_returns.index)\n"
             "comp = {k: v.reindex(common).dropna() for k,v in comp.items()}\n"
             "eq = {k: rt.cumulative_index(v) for k,v in comp.items()}\n"
             "colors = {'Buy & Hold':'#1f77b4','MA200 -> Cash':'#2ca02c'}\n"
             "fig = pl.plot_equity_comparison(eq, 'Buy & Hold vs MA200 -> Cash',\n"
             "    '02_equity_buyhold_vs_timing.png', colors=colors); plt.show()\n"
             "fig = pl.plot_drawdowns(comp, 'Drawdowns: Buy & Hold vs MA200 -> Cash',\n"
             "    '02_drawdowns_timing.png', colors=colors); plt.show()"),
        md("➡️ **Next:** notebook 04 changes one thing — instead of going to *cash* "
           "when below the average, we go to *leveraged* S&P 500. This is the "
           "central idea of the project."),
    ]
    build("03_moving_average_timing.ipynb", cells)


# ===========================================================================
# 04 — leveraged bad-market strategy
# ===========================================================================
def nb04():
    cells = [
        md("# 04 — The Leveraged Bad-Market Strategy\n\n"
           "**The hypothesis.** Bad (below-trend) periods are often followed by "
           "strong rebounds. So instead of going to *cash* when the market is "
           "below its moving average, what if we go to *leveraged* S&P 500 to "
           "capture a bigger recovery?\n\n"
           "> Above the MA → hold **1x** S&P 500.\n"
           "> Below the MA → hold **Lx** daily-leveraged S&P 500 (L = 1.25 … 3.0).\n\n"
           "**Daily leverage** means each day's return is multiplied by L "
           "*and then compounded*: `strategy_return[t] = L * sp500_return[t]` when "
           "below the MA. Compounding daily is what creates **volatility decay** — "
           "we will see it bite here and study it properly in notebook 07.\n\n"
           "**We do not assume it works.** We just measure it honestly."),
        code(SETUP),
        code("from src import data_loader as dl, returns as rt, backtest as bt\n"
             "from src import metrics as mx, plots as pl, config\n\n"
             "underlying, ticker, _ = dl.get_underlying_total_return()\n"
             "u = rt.simple_returns(underlying)\n"
             "rf = dl.get_risk_free_daily(u.index)"),
        md("## Run all leverage levels at the 200-day window"),
        code("rows = []; results = {}\n"
             "for L in config.LEVERAGE_LEVELS:\n"
             "    res = bt.leveraged_bad_market(underlying, u, 200, L, rf_daily=rf,\n"
             "                                  costs=config.ZERO_COSTS)\n"
             "    results[L] = res\n"
             "    srow = res.summary(rf_daily=rf); srow['leverage'] = L\n"
             "    rows.append(srow)\n"
             "tbl = mx.summary_frame(rows)\n"
             "tbl[['leverage','cagr','volatility','sharpe','max_drawdown','calmar']]"),
        md("**Read this table carefully.** As leverage rises, look at what happens "
           "to CAGR versus max drawdown. Typically CAGR barely improves (or even "
           "falls) while the drawdown gets *much* deeper and the Sharpe ratio "
           "*falls*. That is the first hint that the hypothesis is in trouble: the "
           "extra leverage is buying risk, not return."),
        md("## The equity curves and drawdowns"),
        code("bh = bt.buy_and_hold(u, rf_daily=rf)\n"
             "ma200 = bt.ma_to_cash(underlying, u, 200, rf_daily=rf)\n"
             "comp = {'Buy & Hold (1x)': bh.net_returns, 'MA200 -> Cash': ma200.net_returns,\n"
             "        'Lev 1.5x below': results[1.5].net_returns,\n"
             "        'Lev 2x below': results[2.0].net_returns,\n"
             "        'Lev 3x below': results[3.0].net_returns}\n"
             "common = comp['Buy & Hold (1x)'].index\n"
             "for v in comp.values(): common = common.intersection(v.index)\n"
             "comp = {k: v.reindex(common).dropna() for k,v in comp.items()}\n"
             "eq = {k: rt.cumulative_index(v) for k,v in comp.items()}\n"
             "fig = pl.plot_equity_comparison(eq, 'Leveraged bad-market vs baselines (200-day)',\n"
             "    '03_equity_leverage_levels_200d.png'); plt.show()\n"
             "fig = pl.plot_drawdowns(comp, 'Leverage deepens the drawdowns',\n"
             "    '03_drawdowns_leverage.png'); plt.show()"),
        md("Watch the **3x** line: it can lead for years, then a single sustained "
           "bear (2000–02 or 2008–09) sends it down 90%+ and it never catches up. "
           "Leverage applied during *prolonged* declines compounds the losses — "
           "the opposite of the rebound we hoped for.\n\n"
           "➡️ **Next:** notebook 05 sweeps *every* window × leverage combination "
           "and draws heatmaps, so we are not cherry-picking the 200-day case."),
    ]
    build("04_leveraged_bad_market_strategy.ipynb", cells)


# ===========================================================================
# 05 — parameter sweep
# ===========================================================================
def nb05():
    cells = [
        md("# 05 — Parameter Sweep & Heatmaps\n\n"
           "**Goal:** avoid cherry-picking. We run *every* combination of moving-"
           "average window × leverage level × cost assumption, then ask a blunt "
           "question: **does any leveraged version beat buy-and-hold on all of "
           "CAGR, Sharpe, Calmar, and drawdown at once?**"),
        code(SETUP),
        code("from src import data_loader as dl, returns as rt, sweep as sw\n"
             "from src import plots as pl, config\n\n"
             "underlying, ticker, _ = dl.get_underlying_total_return()\n"
             "u = rt.simple_returns(underlying)\n"
             "rf = dl.get_risk_free_daily(u.index)"),
        md("## Run the sweep (gross and net of costs)"),
        code("scenarios = {'gross (0 cost)': config.ZERO_COSTS,\n"
             "             'net (realistic)': config.DEFAULT_COSTS}\n"
             "sweep = sw.run_parameter_sweep(underlying, u, rf_daily=rf,\n"
             "                               cost_scenarios=scenarios)\n"
             "sweep[sweep.strategy=='leveraged_bad_market'][[\n"
             "    'cost_scenario','window','leverage','cagr','sharpe','max_drawdown','calmar']].head(12)"),
        md("## Who beats buy-and-hold?\n\n"
           "`beats_baseline` compares every *genuinely* leveraged config (>1x) to "
           "buy-and-hold. 'Beats all' means strictly better on CAGR **and** Sharpe "
           "**and** Calmar **and** drawdown."),
        code("for label in scenarios:\n"
             "    beats = sw.beats_baseline(sweep, label)\n"
             "    print(f'{label:18s}: beat on CAGR={beats.beats_cagr.sum():2d}, '\n"
             "          f'Sharpe={beats.beats_sharpe.sum():2d}, '\n"
             "          f'Calmar={beats.beats_calmar.sum():2d}, '\n"
             "          f'ALL four={beats.beats_all.sum():2d}  (out of {len(beats)})')"),
        md("The 'ALL four' count is the honest scoreboard. If it is **zero**, then "
           "no leverage setting is unambiguously better than simply holding the "
           "index — higher returns always came with worse risk."),
        md("## Heatmaps: CAGR, Sharpe, max drawdown, Calmar"),
        code("for value, fmt, cbar in [('cagr','.1%','CAGR'), ('sharpe','.2f','Sharpe'),\n"
             "                         ('max_drawdown','.0%','Max drawdown'), ('calmar','.2f','Calmar')]:\n"
             "    mat = sw.heatmap_matrix(sweep, value, 'gross (0 cost)')\n"
             "    mat.index = [config.MA_WINDOW_LABELS.get(w, str(w)) for w in mat.index]\n"
             "    fig = pl.plot_heatmap(mat, f'{cbar} by window & leverage (gross)',\n"
             "        f'04_heatmap_{value}_gross.png', fmt=fmt, xlabel='Leverage below MA',\n"
             "        ylabel='MA window', cbar_label=cbar)\n"
             "    plt.show()"),
        md("The CAGR heatmap may look tempting (greener to the right at low "
           "leverage), but compare it to the drawdown and Calmar heatmaps: risk "
           "rises faster than return as you move right. The best *risk-adjusted* "
           "cells sit at **low or no** leverage.\n\n"
           "➡️ **Next:** notebook 06 checks whether real leveraged ETFs behave "
           "like our synthetic leverage."),
    ]
    build("05_parameter_sweep.ipynb", cells)


# ===========================================================================
# 06 — ETF tests
# ===========================================================================
def nb06():
    cells = [
        md("# 06 — Real Leveraged-ETF Reality Check\n\n"
           "Our backtest assumes we can earn exactly `L × (daily S&P return)` "
           "forever. Real leveraged ETFs only *approximately* do that — they "
           "charge ~0.9% fees, pay financing on borrowed money, and have tracking "
           "error. Here we compare:\n\n"
           "- **Synthetic** leverage (S&P daily return × L), and\n"
           "- **Real** ETFs: **SSO** (2x), **UPRO** (3x), **SPXL** (3x).\n\n"
           "Does synthetic leverage over- or under-state what an investor could "
           "really have captured?"),
        code(SETUP),
        code("from src import data_loader as dl, data_cleaning as dc, returns as rt\n"
             "from src import etf_tests as et, plots as pl, config\n\n"
             "underlying, ticker, _ = dl.get_underlying_total_return()\n"
             "u = rt.simple_returns(underlying)\n"
             "rf = dl.get_risk_free_daily(u.index)\n"
             "raw = dl.load_universe(['SSO','UPRO','SPXL'])\n"
             "clean, _ = dc.clean_universe(raw)"),
        md("## Synthetic vs real, ETF by ETF"),
        code("rows = []\n"
             "for t in ['SSO','UPRO','SPXL']:\n"
             "    if t not in clean: continue\n"
             "    L = config.TICKERS[t]['leverage']; exp = config.TICKERS[t]['expense']\n"
             "    etf_r = rt.simple_returns(clean[t])\n"
             "    cmp = et.compare_synthetic_vs_real(u, etf_r, L, rf_daily=rf, expense_annual=exp)\n"
             "    rows.append({'etf':t,'leverage':L,'realized_beta':cmp['realized_beta'],\n"
             "        'tracking_error_ann':cmp['tracking_error_ann'],\n"
             "        'etf_cagr':cmp['etf_cagr'],'synthetic_costed_cagr':cmp['synthetic_costed_cagr'],\n"
             "        'gap_costed_minus_etf':cmp['gap_costed_minus_etf']})\n"
             "import pandas as pd; pd.DataFrame(rows)"),
        md("**Realized beta** should be close to the ETF's target multiple (≈2 for "
           "SSO, ≈3 for UPRO/SPXL) — confirming they really do track the daily "
           "multiple. The **gap** column shows how much our costed-synthetic CAGR "
           "differs from the real ETF: a small positive number means synthetic "
           "leverage slightly *overstates* reality (the ETFs lag by a bit due to "
           "fees and tracking error)."),
        md("## Picture: synthetic 2x vs the real SSO"),
        code("L = 2.0; etf_r = rt.simple_returns(clean['SSO'])\n"
             "cmp = et.compare_synthetic_vs_real(u, etf_r, L, rf_daily=rf,\n"
             "    expense_annual=config.TICKERS['SSO']['expense'])\n"
             "fig = pl.plot_synthetic_vs_real(cmp['curves'],\n"
             "    'Synthetic 2x vs real SSO (2x)', '06_etf_synth_vs_real_SSO.png')\n"
             "plt.show()"),
        md("The costed-synthetic line tracks the real ETF closely; the gross "
           "(no-cost) synthetic line runs a bit higher — that gap is roughly the "
           "fee + financing drag you actually pay. **Takeaway:** the synthetic "
           "backtest is realistic enough to trust its *conclusions*, and if "
           "anything it is a touch optimistic, so it cannot be hiding a worse "
           "real-world result.\n\n"
           "➡️ **Next:** notebook 07 explains *why* leverage behaved the way it "
           "did, using Monte Carlo and the arithmetic of volatility decay."),
    ]
    build("06_etf_tests.ipynb", cells)


# ===========================================================================
# 07 — Monte Carlo / volatility decay
# ===========================================================================
def nb07():
    cells = [
        md("# 07 — Monte Carlo & Volatility Decay\n\n"
           "**Goal:** understand *when* leverage helps and *when* it destroys "
           "wealth, by simulating thousands of random markets with known drift and "
           "volatility.\n\n"
           "*(This notebook uses a small, fast simulation grid so it runs in "
           "seconds. The full 10,000-path grid lives in `run_all.py`.)*"),
        code(SETUP),
        code("from src import monte_carlo as mc, plots as pl, config"),
        md("## First, the arithmetic — why a flat, choppy market loses money\n\n"
           "Consider one up day of +10% then one down day of −10%:"),
        code("mc.vol_decay_table()"),
        md("A 1x investor ends at 0.99 (−1%). The 2x investor ends at −4%, the 3x "
           "at −9%. The market went nowhere, yet leverage **lost money** — and the "
           "loss grows with the *square* of leverage. That is **volatility "
           "decay**. The closed-form penalty is `0.5 × L² × volatility²` per year:"),
        code("for L in [1,2,3]:\n"
             "    print(f'{L}x at 20% vol: variance drag ≈ {mc.variance_drag(L,0.20):.2%} per year')"),
        md("## The teaching picture: same leverage, two different paths"),
        code("fig = pl.plot_vol_decay_example('volatility_decay_example.png'); plt.show()"),
        md("Left: a choppy flat market — leverage decays. Right: a smooth uptrend "
           "— leverage helps. **The path matters as much as the destination.**"),
        md("## Monte Carlo grid: optimal leverage by drift & volatility\n\n"
           "We simulate many 10-year paths for a range of drifts and volatilities, "
           "apply each leverage to the *same* random draws, and find the leverage "
           "that maximises median terminal wealth."),
        code("# small/fast grid for the notebook: 10-year horizon only, fewer paths\n"
             "# (the full 5-horizon, 10,000-path grid lives in run_all.py)\n"
             "grid = mc.run_grid(horizons_years=[10], n_paths=1500, verbose=False)\n"
             "opt = mc.optimal_leverage_grid(grid, 10, objective='median_terminal')\n"
             "opt.index = [f'{v:.0%}' for v in opt.index]\n"
             "opt.columns = [f'{d:.0%}' for d in opt.columns]\n"
             "fig = pl.plot_heatmap(opt, 'Optimal leverage (max median wealth, 10-yr)',\n"
             "    '07_mc_optimal_leverage.png', fmt='.2g', cmap='viridis',\n"
             "    xlabel='Annual drift', ylabel='Annual volatility', cbar_label='Best leverage')\n"
             "plt.show()"),
        md("**The frontier is diagonal.** High leverage (3x) is optimal only in the "
           "**top-right**: low volatility *and* strong drift. As volatility rises "
           "(moving down), the optimal leverage collapses to **1x** — at 40%+ "
           "volatility you should not leverage at *any* realistic drift.\n\n"
           "**Now connect it to our strategy.** We add leverage when the market is "
           "*below* its moving average — and below-trend periods are exactly the "
           "**high-volatility, low-drift** regimes (bottom-left of this map), where "
           "the optimal leverage is 1x. The strategy leverages precisely where the "
           "math says it should not. That is why it failed on real data."),
        md("## Probability that 2x and 3x beat 1x"),
        code("for L in [2.0, 3.0]:\n"
             "    m = mc.prob_beat_1x_grid(grid, 10, L)\n"
             "    m.index = [f'{v:.0%}' for v in m.index]; m.columns=[f'{d:.0%}' for d in m.columns]\n"
             "    fig = pl.plot_heatmap(m, f'P({L:g}x beats 1x) — 10-yr', f'07_mc_prob_{int(L)}x_beats_1x.png',\n"
             "        fmt='.0%', cmap='RdYlGn', center=0.5, xlabel='Annual drift',\n"
             "        ylabel='Annual volatility', cbar_label='Probability'); plt.show()"),
        md("➡️ **Next:** notebook 08 pulls every headline number together and "
           "states the verdict."),
    ]
    build("07_monte_carlo_volatility_decay.ipynb", cells)


# ===========================================================================
# 08 — final results
# ===========================================================================
def nb08():
    cells = [
        md("# 08 — Final Results & Verdict\n\n"
           "This notebook reads the headline numbers produced by `run_all.py` "
           "(`results/headline_results.json`) and states the conclusion plainly.\n\n"
           "If you have not run the full pipeline yet, run `python run_all.py` from "
           "the project root first."),
        code(SETUP),
        code("import json\n"
             "from src import config\n"
             "with open(config.RESULTS_DIR / 'headline_results.json') as f:\n"
             "    H = json.load(f)\n"
             "print('Sample:', H['data']['underlying_start'], '->', H['data']['underlying_end'],\n"
             "      f\"({H['data']['years']:.1f} years of {H['data']['underlying_ticker']})\")"),
        md("## Baselines vs the best leverage at the 200-day window"),
        code("import pandas as pd\n"
             "bh = H['part1_buy_and_hold']; ma = H['part2_ma_to_cash_200d']\n"
             "lev = H['part3_leveraged_200d']\n"
             "tbl = pd.DataFrame({\n"
             "  'Buy & Hold':   {k: bh[k] for k in ['cagr','volatility','sharpe','max_drawdown','calmar']},\n"
             "  'MA200 -> Cash':{k: ma[k] for k in ['cagr','volatility','sharpe','max_drawdown','calmar']},\n"
             "  'Lev 1.5x':     lev['1.5x'], 'Lev 2x': lev['2x'], 'Lev 3x': lev['3x'],\n"
             "}).T\n"
             "tbl"),
        md("## Did any leveraged config beat buy-and-hold on everything?"),
        code("print('Configs beating buy & hold on ALL of CAGR/Sharpe/Calmar/drawdown:')\n"
             "print('  gross (0 cost):', H['part4_beats_all_count_gross'])\n"
             "print('  net (realistic):', H['part4_beats_all_count_net'])\n"
             "print()\n"
             "print('Fraction of historical periods where 2x leverage beat buy & hold (total return):',\n"
             "      f\"{H['part5_periods_leverage_helped_frac']:.0%}\")"),
        md("## The Monte Carlo verdict at an S&P-like point"),
        code("sp = H['part7_sp_like_point']\n"
             "print(f\"S&P-like world: drift={sp['drift']:.0%}, vol={sp['vol']:.0%}\")\n"
             "print('Median CAGR by leverage :', sp['median_cagr_by_leverage'])\n"
             "print('P(beat 1x) by leverage  :', sp['prob_beat_1x_by_leverage'])\n"
             "print('Optimal leverage (iid)  :', H['part7_sp_like_optimal_leverage'])"),
        md("## The verdict\n\n"
           "Putting it together (your exact numbers may differ slightly by data "
           "vintage):\n\n"
           "1. **Does leverage in bad markets beat buy-and-hold?** Not on a "
           "risk-adjusted basis. Zero configurations beat buy-and-hold on all four "
           "metrics at once. Low leverage (1.25–1.5x) can nudge CAGR up a little, "
           "but always with a *disproportionately* deeper drawdown.\n\n"
           "2. **Does it beat the moving-average-to-cash rule?** No. The classic "
           "Faber rule has the best Sharpe and by far the shallowest drawdowns. "
           "Adding leverage moves you in the wrong direction.\n\n"
           "3. **Which moving average / leverage is 'best'?** ~200 days is the most "
           "robust window; the best *risk-adjusted* leverage is **1x** (i.e. no "
           "leverage). Leverage only ever helped in specific fast-rebound regimes "
           "(post-2009 dips, the COVID crash), not on average.\n\n"
           "4. **When does volatility decay destroy returns?** Whenever volatility "
           "is high — exactly the below-trend regimes the strategy leverages. The "
           "Monte Carlo map shows leverage only pays in low-vol, positive-drift "
           "markets.\n\n"
           "**Bottom line:** the idea is intuitive but the data rejects it. It is a "
           "good example of a hypothesis that sounds clever and fails an honest "
           "test. The full discussion is in `reports/research_paper.md`."),
    ]
    build("08_final_results.ipynb", cells)


def main():
    print("Building notebooks ...")
    nb01(); nb02(); nb03(); nb04(); nb05(); nb06(); nb07(); nb08()
    print("Done.")


if __name__ == "__main__":
    main()
