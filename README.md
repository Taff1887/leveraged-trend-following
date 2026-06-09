# Trend Following, Leveraged Re-Entry, and Volatility Decay

### Can daily leveraged S&P 500 exposure improve long-term returns?

A small, readable, **reproducible** quantitative-research project that honestly
tests a tempting idea — and finds that it does not work. Built from scratch in
Python (no black-box backtesting frameworks) so a beginner can read the code and
the paper from start to finish.

> ⚠️ **Educational research only — not investment advice.** Leveraged ETFs are
> high-risk and can lose most of their value.

---

## The hypothesis

The classic **Faber trend rule** holds the S&P 500 when it is above its long
moving average and **moves to cash** when it falls below. This project tests a
twist:

> **When the S&P 500 is *below* its moving average, hold *daily-leveraged* S&P 500
> instead of cash** — on the theory that bad markets are followed by strong
> rebounds that leverage could amplify.

| | Above the moving average | Below the moving average |
|---|---|---|
| Buy & Hold | 1× | 1× |
| MA → Cash (Faber) | 1× | cash (T-bills) |
| **This project** | **1×** | **L× daily leverage** (L = 1.25 … 3.0) |

We test leverage **1.0, 1.25, 1.5, 2.0, 2.5, 3.0×** and moving-average windows of
**50, 100, 150, 200, 210, 250, 252 days**, gross and net of realistic costs — and
we do **not** assume it works.

## Headline result: it doesn't beat buy-and-hold

S&P 500 total return, 1988–2026 (38 years), gross of costs:

| Strategy | CAGR | Volatility | Sharpe | Max drawdown | Calmar |
|---|---|---|---|---|---|
| Buy & Hold (1×) | 11.5% | 17.9% | 0.54 | −55% | 0.21 |
| **MA200 → Cash** (Faber) | 10.2% | 11.8% | **0.64** | **−21%** | **0.50** |
| Lev 1.5× below MA | 11.6% | 23.4% | 0.47 | −71% | 0.16 |
| Lev 2× below MA | 11.2% | 29.4% | 0.41 | −83% | 0.14 |
| Lev 3× below MA | 9.0% | 42.0% | 0.35 | −96% | 0.09 |

* **0 of 35** genuinely-leveraged configurations beat buy-and-hold on all of
  CAGR / Sharpe / Calmar / drawdown — and **0** beat it on Sharpe — gross *or*
  net of costs.
* Leverage barely changes CAGR but **massively deepens drawdowns** and **lowers
  Sharpe**.
* The **original move-to-cash rule is the risk-adjusted winner.**

**Why?** Daily leverage suffers **volatility decay** (≈ ½·L²·σ² per year). The
strategy leverages *below-trend* markets — the **highest-volatility** regimes —
so it applies leverage exactly where the math says not to.

<p align="center">
<img src="charts/03_equity_leverage_levels_200d.png" width="80%">
</p>

The 3× line leads into 2000, then collapses ~96% in the 2008 bear and never
recovers its lead. A 10,000-path Monte Carlo shows leverage only pays in
**low-volatility, positive-drift** markets:

<p align="center">
<img src="charts/07_mc_optimal_leverage.png" width="70%">
</p>

(Optimal leverage is high only in the top-right — low vol, high drift. Below-trend
"bad markets" live in the high-vol bottom rows, where the optimum is **1×**.)

## How the strategy works (no look-ahead)

For each day *t*:

1. Compute the moving average from prices **up to yesterday** (`t−1`).
2. If yesterday's price was **above** its MA → today's exposure = **1×**.
   If **below** → today's exposure = **L×**.
3. `strategy_return[t] = exposure[t] × sp500_return[t]`, minus optional costs.
4. Compound daily — so **volatility decay is captured automatically**.

The signal is lagged one day everywhere, so we never trade on information we
could not have had.

## Repository layout

```
README.md                  ← you are here
requirements.txt
run_all.py                 ← regenerates ALL results + charts
build_notebooks.py         ← regenerates the 8 notebooks from source
data/
  raw/                     ← cached Yahoo Finance downloads (one CSV per ticker)
src/
  config.py                ← all paths, tickers, parameters, cost assumptions
  data_loader.py           ← download + cache (with offline synthetic fallback)
  data_cleaning.py         ← clean/align series + data-summary table
  returns.py               ← prices → returns → cumulative index
  signals.py               ← moving-average trend signal (lagged)
  backtest.py              ← from-scratch daily backtester
  metrics.py               ← CAGR, vol, Sharpe, Sortino, drawdown, Calmar, ...
  sweep.py                 ← parameter sweep + period/episode analysis
  plots.py                 ← all charts
  monte_carlo.py           ← volatility-decay / optimal-leverage simulations
  etf_tests.py             ← synthetic leverage vs real leveraged ETFs
notebooks/                 ← 01…08, runnable in order, beginner → advanced
charts/                    ← all figures (.png)
results/                   ← all result tables (.csv) + headline_results.json
reports/
  research_paper.md        ← the full 20-section study
  executive_summary.md     ← one-page summary
```

## Install

```bash
git clone <this-repo>
cd leveraged-trend-following
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Requires Python 3.10+.

## Run the analysis

```bash
# Reproduce every table (results/) and chart (charts/) and the headline JSON.
# Uses cached data in data/raw; downloads from Yahoo Finance on first run.
python run_all.py

# Quicker run with a smaller Monte Carlo grid:
python run_all.py --fast
# Or set the number of Monte Carlo paths explicitly:
python run_all.py --mc-paths 10000
```

## Reproduce the charts / notebooks

* Charts are written to `charts/` by `python run_all.py`.
* Run the test suite with `python -m pytest tests/ -q` (9 fast sanity tests
  covering volatility-decay arithmetic, the no-look-ahead lag, and the metric
  formulas).
* Rebuild the PDF (optional, needs `pip install markdown-pdf pymupdf`):
  `python build_pdf.py`.
* The eight teaching notebooks are generated by `python build_notebooks.py` and
  are designed to be read **in order**:

| Notebook | Topic |
|---|---|
| 01 | Load & clean the S&P 500 total-return data |
| 02 | Buy-and-hold baseline and how every metric is defined |
| 03 | Moving-average timing (the Faber move-to-cash rule) |
| 04 | The leveraged bad-market strategy |
| 05 | Parameter sweep + heatmaps (no cherry-picking) |
| 06 | Real leveraged-ETF reality check (SSO / UPRO / SPXL) |
| 07 | Monte Carlo & volatility decay |
| 08 | Final results & verdict |

## Data

* **Primary:** `^SP500TR` — true daily S&P 500 **total return** (1988+).
* **Long-history context:** `^GSPC` price index (1927+, dividends excluded).
* **Risk-free / financing:** `^IRX` 13-week T-bill (1960+).
* **Real leveraged ETFs:** SSO (2×), UPRO (3×), SPXL (3×); 1× proxies SPY/IVV/SPLG/VOO.

All from Yahoo Finance via `yfinance`, cached locally. New tickers can be added by
editing one dictionary in `src/config.py`. If you are offline, the loader falls
back to a clearly-labelled synthetic series so the pipeline still runs (no results
in the paper use it). Full provenance: `results/data_summary.csv`.

## Key limitations

* True daily *total-return* data starts in 1988 (one ~38-year sample).
* Leveraged ETFs are young (2006–2009) and born into a bull market.
* Monte Carlo uses constant drift/vol with i.i.d. (optionally fat-tailed) shocks;
  real volatility clustering makes leverage in bad regimes *worse*, not better.
* US-centric single index; no taxes.

See [`reports/research_paper.md`](reports/research_paper.md) §19 for the full list.

## What I'd build next

The result inverts the hypothesis: **leverage belongs in calm uptrends, not
volatile downtrends.** Natural follow-ups: leverage *above* the MA / de-risk
below it; **volatility targeting** (`target_vol / realized_vol`); multi-timeframe
trend signals; longer and international histories.

---

*Built as an educational, reproducible research project. Not investment advice.*
