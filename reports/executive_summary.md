# Executive Summary

**Project:** *Trend Following, Leveraged Re-Entry, and Volatility Decay — Can
daily-leveraged S&P 500 exposure improve long-term returns?*
**Signal:** one only — the 200-day moving average (the daily twin of Mebane
Faber's 10-month rule).
**Sample:** S&P 500 **total return**, daily 1928–2026 (real `^SP500TR` from 1988,
real `^GSPC` + real Shiller dividends before); real T-bills throughout.

---

### The question

Use the 200-day MA to switch between leveraged and ordinary S&P 500 exposure.
Does it beat buy-and-hold and the classic move-to-cash rule — and on *which*
yardstick?

### The headline: the answer depends on the yardstick

Full history (1928–2026, net of costs):

| Strategy | Grew $1 to | CAGR | Sharpe | **IR vs S&P** | Max DD |
|---|---|---|---|---|---|
| Buy & Hold 1× (S&P) | $13,021 | 10.1% | 0.43 | — | −84% |
| **MA200 → Cash** (Faber) | $25,922 | 11.0% | **0.63** | **~0.00** | −46% |
| Lev 2× above MA | $655,939 | 14.8% | 0.51 | 0.53 | −89% |
| **Lev 4× above MA** | **$87,028,073** | **20.7%** | 0.56 | **0.57** | −99% |

Three benchmarks, **three different winners**:

* **On Sharpe — the 200-day move-to-cash rule is very hard to beat** (0.63 vs the
  S&P's 0.43), with less than half the drawdown. As a *standalone, risk-adjusted*
  strategy it is the best thing in the study.
* **On information ratio it is easily beaten.** Move-to-cash has a roughly **zero
  (recently *negative*) IR versus the S&P** — as a bet against the index it has
  actually *lagged* throughout the bull market. **Leveraging the uptrend** posts a
  large positive IR (0.47 → 0.57, rising with leverage) — i.e. it adds genuine
  return *relative to the index*.
* **And the leverage strategy also beats the S&P on Sharpe** (0.51–0.56 vs 0.43)
  while compounding $1 into the millions — so for an investor benchmarked against
  the S&P, leveraging the uptrend dominates buy-and-hold on essentially every
  measure except maximum drawdown.

### Key findings

1. **Direction is everything.** Leverage the *uptrend* (Lx **above** the MA, 1x
   below) and you beat buy-and-hold on CAGR, Sharpe, Sortino, Calmar and IR.
   Leverage the *downtrend* ("buy the dip" below the MA) and 3× turns $1 into
   **$0.79** — the 200-day MA fires at the *start* of declines, not the bottom.
2. **The trend filter — not the leverage — is what pays.** Held *constantly*, 4×
   leverage grows $1 to just **$54** over a century (and was wiped out in 1987);
   the same 4× *switched* by the MA grows $1 to **$87 million**.
3. **Leverage works spectacularly if you can time a bottom** — 3× off the COVID
   low returned **+372%** in a year — but the bottom is only obvious in hindsight.
4. **Volatility decay caps it.** For the recent S&P (mean ~16%, vol ~18%) the
   leverage at which decay flattens the total return is ≈ **10×**.
5. **Honest caveats.** Leveraging the uptrend carries **far deeper drawdowns**
   (−86% to −99%), and it does **not** beat plain move-to-cash on Sharpe. A
   "cash-on-sharp-drops" 3-tier variant protects against bears but **whipsaws** in
   bull markets. Real leveraged ETFs (SSO/UPRO/SPXL) confirm the synthetic results
   and, if anything, the synthetic version is slightly *optimistic*.

### Bottom line

* **Optimising Sharpe / capital preservation →** the plain 200-day **move-to-cash**
  rule. Hard to beat on risk-adjusted terms; it just doesn't try to beat the index.
* **Benchmarked against the S&P and willing to tolerate deep drawdowns →**
  **leverage the uptrend** modestly (~1.5–2×): a higher Sharpe than the index, a
  large information ratio, and dramatically higher growth — never the reverse
  ("buy the dip with leverage"), which is the worst rule of all.

---
*Full study and every per-horizon table: [`research_paper.md`](research_paper.md).
Educational research only — not investment advice.*
