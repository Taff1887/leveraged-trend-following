# Trend Following, Leveraged Re-Entry, and Volatility Decay

### *(working title — headline to be finalised)*

A reproducible, beginner-friendly study of whether **switching between
daily-leveraged and ordinary S&P 500 exposure**, timed by a single 200-day
moving average (the daily equivalent of Faber's 10-month rule), can improve
long-term returns — tested honestly on total-return data going back as far as the
record allows.

> **Disclaimer.** Educational research only, not investment advice. Leveraged
> ETFs are high-risk and can lose most of their value. Past performance — real or
> simulated — does not predict the future.
>
> *Note on framing: this version follows the analysis step by step and leads with
> the methodology and evidence. The abstract/headline below is provisional.*

---

## How this study is structured

We deliberately test **only one trend signal — the 200-day moving average** —
exactly as Faber popularised it (his rule is the 10-month SMA on monthly data;
200 days is its daily twin). The argument is built in six steps:

1. **Buy & hold vs the Faber moving-average rule.** Establish that the simple
   trend rule improves *risk-adjusted* returns.
2. **Leverage returns.** Define daily leverage and show what *constant* 1.5×/
   2.5×/3× exposure does to the index and versus the trend rule.
3. **Volatility decay — and timing.** Explain the decay, then show that buying
   leverage *at major market lows* (GFC, COVID, 2022, 2025) pays enormously — so
   leverage can help *if you time it*.
4. **How much leverage is "too much"?** Map, against trend and volatility, the
   leverage at which volatility decay exactly cancels the return (flat), and the
   leverage that merely ties 1×.
5. **The switching strategy.** Use the 200-day MA to switch leverage on and off.
   Test the intuitive *"buy leverage low"* version (leverage below the MA), then
   **check whether doing it the other way round is better** (leverage above the
   MA). Full metrics tables and equity/drawdown plots.
6. **Robustness & verdict.** Monte Carlo optimal leverage, real leveraged ETFs,
   costs, sub-periods, limitations.

---

## Data

Everything is total return (dividends reinvested), from standard public sources,
cached locally for reproducibility.

| Series | Span | Role |
|---|---|---|
| **Shiller** monthly S&P price + dividends | 1871–present | reconstruct monthly total return for the Faber replication |
| **Reconstructed daily total return** (`^GSPC` price + Shiller dividend yield) | 1928–1988 | early daily history |
| **Real `^SP500TR`** (true daily total return) | 1988–2026 | spliced on |
| **`^IRX`** 13-week T-bill (+ 3.5% constant before 1960) | cash / financing |

**Reconstruction check.** Over 1988–2026 the reconstructed daily total return
tracks the *real* `^SP500TR` with **0.50%/yr** tracking error, **0.9996**
correlation (CAGR 11.41% vs 11.47%). The full-period (1928+) max drawdown of
−83.9% matches the 1929–32 crash, consistent with Faber's −83.66%. The long daily
series is therefore safe to use, and we apply **true daily leverage** to it.

---

## Step 1 — Buy & hold vs the Faber moving-average rule

**The rule (Faber):** at each month-end, if the index is above its 10-month SMA,
hold the S&P 500; otherwise move to cash (T-bills). We replicate it exactly, then
use the daily 200-day twin for the rest of the study. The signal is always lagged
(we trade on yesterday's close), so there is no look-ahead.

**Monthly replication, 1901–2026** (Faber's setup):

| Metric | S&P 500 buy & hold | 10-month timing → cash |
|---|---|---|
| CAGR | 9.95% | 11.24% |
| Volatility | 15.4% | 10.8% |
| Sharpe | 0.44 | **0.69** |
| **Max drawdown** | **−81.8%** | **−43.0%** |

Faber's published figures are −83.66% → −42.24% for the same drawdowns — we land
within a point, confirming the replication is faithful.

![Faber replication](../charts/F0_faber_replication.png)

**Daily 200-day version, 1928–2026:**

| Metric | Buy & Hold 1× | MA200 → Cash |
|---|---|---|
| CAGR | 10.14% | 11.29% |
| Volatility | 18.9% | 12.6% |
| Sharpe | 0.40 | **0.60** |
| Sortino | 0.56 | **0.84** |
| Max drawdown | −83.9% | **−46.2%** |
| Calmar | 0.12 | **0.24** |

![Buy & hold vs 200-day MA](../charts/F1_baseline_equity.png)
![Drawdowns](../charts/F1_baseline_drawdowns.png)

**Takeaway:** the trend rule keeps essentially all of the return while cutting
volatility by a third and *halving* the worst drawdown — Sharpe, Sortino, and
Calmar all jump. **The 200-day MA clearly adds risk-adjusted value.** That is the
foundation everything else builds on.

---

## Step 2 — Leverage returns

**What "daily leverage" means.** A daily L× fund multiplies each *day's* return by
L and rebalances: `r_lev[t] = L · r_index[t]` (before fees/financing). It is *not*
L× the multi-day return — the difference, after compounding, is volatility decay
(Step 3). Borrowed money costs the broker call / financing rate, and leveraged
ETFs charge ~0.9%/yr; we include both.

Holding *constant* daily leverage on the index over the full history (net of
costs):

| | CAGR |
|---|---|
| 1× (buy & hold) | 10.14% |
| Always 1.5× | 10.46% |
| Always 2.5× | 10.15% |
| Always 3× | **8.43%** |

![Constant leverage on the index](../charts/F2_leverage_on_index.png)

**Takeaway:** constant leverage barely helps at 1.5× and *loses* by 3×. Across a
full century — including 1929 and 2008 — naive "just hold 3×" underperforms plain
buy & hold, and badly trails the trend rule. Something is eating the extra
exposure. That something is volatility decay.

---

## Step 3 — Volatility decay, and why *timing* matters

**The arithmetic.** A +10% day followed by a −10% day:

| | 1× | 2× | 3× |
|---|---|---|---|
| Two-day return | −1.0% | −4.0% | −9.0% |

The market round-trips to roughly flat, but leverage loses — and the loss grows
with the *square* of leverage. The annual penalty is the **variance drag**
≈ ½·L²·σ²: at 20% volatility that is ~2%/yr for 1×, **8%/yr for 2×, 18%/yr for
3×**.

![Volatility decay](../charts/volatility_decay_example.png)

**But decay is a property of choppy/falling markets.** In a smooth uptrend,
leverage amplifies gains. The sharpest example is buying leverage at a **market
bottom**, where the rebound is steep and one-directional. Forward **1-year**
total return if you had bought at the exact low:

| Bottom | 1× | 1.5× | 2× | 3× |
|---|---|---|---|---|
| GFC (2009-03-09) | +72% | +122% | +182% | **+339%** |
| COVID (2020-03-23) | +78% | +132% | +198% | **+372%** |
| 2022 (2022-10-12) | +23% | +35% | +47% | +72% |
| 2025 tariff selloff (2025-04-08) | +39% | +61% | +87% | **+146%** |

![Buying leverage at the lows](../charts/F5_buy_leverage_at_lows.png)

**Takeaway:** leverage absolutely *can* work in your favour — **if you time it**,
buying into the violent recovery off a low. The catch, which drives the rest of
the paper: *the low is only obvious in hindsight.* The question is whether a
simple, rules-based signal (the 200-day MA) can capture enough of that timing to
make leverage pay — without knowing the bottom in advance.

---

## Step 4 — How much leverage is "too much"?

Two closed-form leverage thresholds, each a function of the trend (the 1× CAGR
`g`) and the annual volatility `σ`. Both are confirmed by Monte Carlo.

**(a) The "flat total return" leverage.** Leveraged compound growth is
`g(L) = L·μ − ½·L²·σ²`. Setting it to zero gives the leverage at which volatility
decay exactly eats the whole trend:

$$L_{\text{zero}} = \frac{2g}{\sigma^2} + 1.$$

Below it, leverage still grows; above it, you **lose money** outright; far above
it (e.g. ~10×+) you are effectively wiped out. For the S&P over the **last 10
years** (CAGR 15.3%, vol 18.1%), the flat-return leverage is **≈ 10.4×** — which
is why a hypothetical "10×" S&P fund would have gone essentially nowhere despite a
strong decade.

![Zero-return leverage map](../charts/F3_zero_return_leverage_map.png)

**(b) The "matches 1×" leverage.** The leverage whose compound return merely
*ties* buy & hold is `L = 2μ/σ² − 1` (in excess-return terms). For the S&P
(excess drift 7.4%, vol 18.9%) that is **≈ 3.1×**, with the growth-optimal
**Kelly** leverage `μ/σ² ≈ 2.1×` sitting exactly halfway between 1× and the
break-even.

![Break-even leverage map](../charts/F3_breakeven_leverage_map.png)

A fine-grid Monte Carlo lands precisely on the closed form — median CAGR peaks at
Kelly and returns to the 1× level at break-even:

![Optimal-leverage curve](../charts/F3_optimal_leverage_curve.png)

**Takeaway:** for the S&P's drift and volatility, *steady* leverage beyond ~2×
(Kelly) buys little extra growth, beyond ~3× you fall behind 1×, and around ~10×
you make nothing. Leverage has a sweet spot that depends entirely on the
trend-to-volatility ratio. Since the trend rule lets us choose *when* to be
leveraged, the natural idea is to apply leverage only when conditions are
favourable.

---

## Step 5 — The switching strategy (200-day MA)

We now switch between **daily-leveraged** and **ordinary 1×** S&P exposure using
the 200-day MA. There are two opposite ways to do it, and we test both.

**Strategy A — "buy leverage low" (leverage BELOW the MA).** When the market is
below trend (cheap, "on sale"), hold L× leverage to ride the rebound; when above
trend, hold plain 1×. This is the intuitive version motivated by the
bought-the-low event studies in Step 3.

**Strategy B — "the other way" (leverage ABOVE the MA).** Leverage the calm,
above-trend regime; drop to plain 1× when the market falls below trend.

Full history (1928–2026), **net of costs**, both directions at every level:

| Strategy | CAGR | Vol | Sharpe | Sortino | Max DD | Calmar |
|---|---|---|---|---|---|---|
| Buy & Hold 1× | 10.1% | 18.9% | 0.40 | 0.56 | −83.9% | 0.12 |
| MA200 → Cash | 11.3% | 12.6% | **0.60** | **0.84** | **−46.2%** | **0.24** |
| **A: Lev 1.5× BELOW** | 7.9% | 24.7% | 0.27 | 0.38 | −94.3% | 0.08 |
| **A: Lev 2× BELOW** | 5.7% | 31.0% | 0.21 | 0.29 | −98.2% | 0.06 |
| **A: Lev 3× BELOW** | −0.2% | 44.3% | 0.13 | 0.19 | −99.9% | −0.00 |
| **B: Lev 1.5× ABOVE** | 11.9% | 23.6% | 0.43 | 0.60 | −85.7% | 0.14 |
| **B: Lev 2× ABOVE** | 14.2% | 28.9% | 0.47 | 0.66 | −89.2% | 0.16 |
| **B: Lev 3× ABOVE** | **17.5%** | 40.4% | 0.50 | 0.71 | −95.7% | 0.18 |

![Leverage above the MA vs baselines](../charts/F4_inverted_equity.png)
![Drawdowns](../charts/F4_inverted_drawdowns.png)

**The intuitive idea fails.** Strategy A ("buy leverage low") gets *worse* as
leverage rises — 1.5× below trails buy & hold, 2× below earns just 5.7%, and 3×
below actually *loses money* (−0.2% CAGR) with a −99.9% drawdown. Why? The 200-day
MA does **not** buy the bottom. It flags "below trend" at the *start* of a
decline, when the market is still highly volatile and often has much further to
fall (1929, 2000–02, 2008). So Strategy A piles leverage into exactly the
high-volatility, still-falling regime where decay is worst — the opposite of the
clean bought-the-low trades in Step 3.

**The other way is far better.** Strategy B (leverage the uptrend) *improves* with
leverage and beats buy & hold on CAGR, Sharpe, Sortino, and Calmar at every
level. At 2×, the two directions of the *same idea* differ enormously — Sharpe
0.47 vs 0.21, CAGR 14.2% vs 5.7%:

![Direction comparison](../charts/F4_direction_comparison.png)

**A closer look — 2000–2026** (drops the un-survivable 1929/1987 single-day
crashes; net of costs):

| Strategy | CAGR | Sharpe | Max DD | Calmar |
|---|---|---|---|---|
| Buy & Hold 1× | 8.3% | 0.41 | −55.3% | 0.15 |
| MA200 → Cash | 7.5% | **0.52** | **−20.6%** | **0.36** |
| Lev 1.5× ABOVE | 9.5% | 0.43 | −59.0% | 0.16 |
| Lev 2× ABOVE | 11.1% | 0.45 | −62.8% | 0.18 |
| Lev 3× ABOVE | 13.4% | 0.47 | −73.5% | 0.18 |
| Lev 2× BELOW *(A)* | 5.7% | 0.28 | −85.9% | 0.07 |

Post-2000 the ranking is identical and the above-MA drawdowns are far more
survivable (3× peaks at −74% rather than −96%).

**Two important caveats on Strategy B.**
1. It beats buy & hold on every *ratio*, but it has **deeper maximum drawdowns**
   than buy & hold — you are leveraged *going into* fast crashes the MA can't
   dodge in time (a −22% day at 3× is −66% in one day).
2. It does **not** beat the plain move-to-cash rule on a risk-adjusted basis:
   MA200→cash still has the best Sharpe, Sortino, Calmar, and (by far) the
   shallowest drawdown.

---

## Step 6 — Robustness & verdict

**Monte Carlo (optimal leverage by regime).** Simulating 10,000 paths across a
grid of drifts and volatilities shows the same diagonal frontier: high leverage
only pays in **low-volatility, positive-drift** regimes; at ≥30–40% volatility the
optimum collapses to 1×. Below-trend markets are precisely the high-volatility
rows — which is why Strategy A fails and Strategy B (leveraging the calm,
above-trend rows) works.

![Optimal leverage by drift and volatility](../charts/07_mc_optimal_leverage.png)

**Real leveraged ETFs.** SSO (2×), UPRO/SPXL (3×) track their daily multiple
closely — realized betas 1.95 / 2.97 / 2.93 — with 3.1–4.6%/yr tracking error,
and our costed *synthetic* leverage slightly *overstates* the real ETFs (by
0.3–0.6%/yr). So the synthetic results are, if anything, a touch optimistic; real
products would not have done better.

![Synthetic vs real SSO](../charts/06_etf_synth_vs_real_SSO.png)

**Costs matter for Strategy B.** Because B is leveraged ~70% of the time,
financing is a real drag: 3× above-MA falls from 26.8% CAGR gross to 17.5% net.
All Strategy-B numbers above are net of expense + financing + turnover.

**Verdict (provisional — headline to be finalised).**
* The **200-day MA adds genuine value**: move-to-cash is the best *risk-adjusted*
  rule tested (Sharpe 0.60, drawdown −46%).
* **Leverage can work, but only with the right timing and direction.** Buying
  leverage at true lows is spectacular but unknowable in advance; the MA's
  "below-trend" signal is the *wrong* time to leverage (high volatility, still
  falling), so the intuitive "buy leverage low" rule fails.
* **Leveraging the *uptrend* (above the MA) is the productive direction** — it
  beats buy & hold on CAGR/Sharpe/Sortino/Calmar across ~100 years — but at the
  cost of deeper drawdowns, and it still does not beat simple move-to-cash on
  risk-adjusted terms.
* Practical reading: trend-following is fundamentally a *risk-reducer*; *if* you
  add leverage, add it **modestly (~1.5–2×) above the trend**, never below it.

---

## Limitations

* True daily *total* return begins in 1988; pre-1988 daily history is a validated
  reconstruction (0.5%/yr tracking error), and the pre-1960 cash rate is a
  documented constant.
* Daily-leverage modelling assumes execution at the close with a fixed cost;
  real financing spreads, borrow availability, and slippage vary over time.
* Real leveraged ETFs are young (2006–2009) and born into a bull market.
* The Monte Carlo uses constant drift/volatility with i.i.d. (optionally
  fat-tailed) shocks; real volatility clustering punishes leverage *more*, so the
  i.i.d. "optimal leverage" is generous.
* US-only, single index, no taxes. One ~100-year path is still one sample.

**Future work.** Volatility targeting (scale leverage by `target_vol /
realized_vol`) to tame Strategy B's deep drawdowns; multi-timeframe trend signals;
international and longer histories; explicit taxes.

---

### Reproducibility

```bash
pip install -r requirements.txt
python run_all.py            # broader sweep, Monte Carlo, ETF tests (supplementary)
python run_faber_leverage.py # this paper: Faber replication, maps, event studies, switching
python build_notebooks.py    # rebuilds notebooks/01..09
python -m pytest tests/ -q   # 11 sanity tests
python build_pdf.py          # optional: rebuild this PDF
```

Figures are PNGs in `charts/`; numbers are in `results/` (this paper's headline
JSON is `results/headline_faber.json`; the supplementary sweep is
`results/headline_results.json`). Data is cached in `data/raw` (including the
Shiller spreadsheet). Random seeds are fixed in `src/config.py`.

*Educational research only — not investment advice.*
