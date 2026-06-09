# Executive Summary

**Project:** *Trend Following, Leveraged Re-Entry, and Volatility Decay — Can
Daily Leveraged S&P 500 Exposure Improve Long-Term Returns?*

**Sample:** S&P 500 total return (`^SP500TR`), daily, 1988–2026 (38.4 years).

---

### The question

The classic Faber trend rule holds the S&P 500 when it is above its long moving
average and **moves to cash** when it falls below. We tested an aggressive
alternative: when the market is **below** trend, rotate into **daily-leveraged**
S&P 500 exposure (1.25× to 3×) instead of cash, betting that weak markets are
followed by strong rebounds that leverage can amplify.

### The verdict: the idea does not work

| | Buy & Hold | MA200 → Cash | Lev 2× below MA |
|---|---|---|---|
| CAGR | 11.5% | 10.2% | 11.2% |
| Sharpe (vs T-bill) | 0.54 | **0.64** | 0.41 |
| Max drawdown | −55% | **−21%** | **−83%** |
| Calmar | 0.21 | **0.50** | 0.14 |

* **0 of 35** genuinely-leveraged configurations beat buy-and-hold on **all** of
  CAGR, Sharpe, Calmar, and drawdown — and **0** beat it on Sharpe alone — whether
  gross or net of realistic costs.
* Adding leverage **barely changes CAGR** (and lowers it above ~1.5×) while
  **drastically deepening drawdowns** (−55% → −96% at 3×) and steadily lowering
  the Sharpe ratio.
* The **original move-to-cash rule remains the risk-adjusted winner** by a wide
  margin.

### Why it fails (the one-sentence mechanism)

Daily leverage suffers **volatility decay** — a drag of roughly
½ × leverage² × volatility² per year. The strategy switches leverage on
**below-trend** markets, which are precisely the **highest-volatility** regimes,
so it deploys leverage exactly where the mathematics says not to. A 10,000-path
Monte Carlo confirms leverage only pays in **low-volatility, positive-drift**
markets; at ≥40% volatility (typical of crashes) leverage is near-total wipeout.

### Nuance (the honest part)

Leverage **did** help in the **post-2009 era of shallow, V-shaped dips** and in
the **2020 COVID crash** specifically — fast rebounds reward leverage. But across
every *prolonged* bear (1929, 1970s, 1987, dot-com, 2008, 2022) leverage made
losses far worse. The wins are a **regime, not a rule.**

### Reality check

Real leveraged ETFs (SSO 2×, UPRO/SPXL 3×) track their daily multiple closely
(realized β = 1.95 / 2.97 / 2.93) with only 0.3–0.6%/yr of extra drag versus
synthetic leverage — so the synthetic backtest, if anything, **flatters**
leverage, and leverage still loses.

### Part II — following Faber faithfully, and fixing the direction

We then replicated Faber's *actual* method (monthly, 10-month SMA, total return
back to **1901**) — matching his published drawdowns to within a point (timing
−43.0% vs his −42.24%; buy-hold −81.8% vs −83.66%) — and tested the **inverted**
rule on data back to **1928**: leverage *above* the trend, 1× below.

| (1928–2026, net) | CAGR | Sharpe | Max DD | Calmar |
|---|---|---|---|---|
| Buy & Hold 1× | 10.1% | 0.40 | −84% | 0.12 |
| MA200 → Cash | 11.3% | **0.60** | **−46%** | **0.24** |
| **Lev 2× ABOVE MA** | **14.2%** | **0.47** | −89% | 0.16 |
| Lev 2× BELOW MA (Part I) | 5.7% | 0.21 | −98% | 0.06 |

**Inverting the rule roughly doubles the Sharpe and triples the CAGR** versus
leveraging below trend, and beats buy-and-hold on CAGR, Sharpe, and Calmar —
*confirming the constructive takeaway*. The closed-form/Monte-Carlo optimum for
the S&P is **Kelly ≈ 2×** (break-even ≈ 3.1×). Caveats: leverage-above-MA still
has **deeper drawdowns** than buy-and-hold (you're leveraged going into crashes)
and **never beats plain move-to-cash** on risk-adjusted terms. So: trend-following
is fundamentally a risk-reducer; *if* you add leverage, add it modestly (~1.5–2×)
**above** the trend, never below.

---
*Full study: [`research_paper.md`](research_paper.md) (Part II covers the Faber
replication and inverted strategy). Educational research only — not investment
advice.*
