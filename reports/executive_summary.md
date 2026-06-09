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

### Constructive takeaway

The result inverts the hypothesis: **leverage belongs in calm uptrends, not
volatile downtrends.** The natural follow-up — leverage *above* the MA, de-risk
below it, or volatility-target the exposure — is left for future work.

---
*Full study: [`research_paper.md`](research_paper.md). Educational research only —
not investment advice.*
