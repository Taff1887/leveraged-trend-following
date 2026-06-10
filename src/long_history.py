"""
long_history.py
===============

Builds the LONGEST total-return S&P 500 series we can, so we can follow Mebane
Faber's paper (which tests the S&P 500 monthly back to 1901) instead of being
stuck with Yahoo's 1988 total-return start.

Two sources, both standard and public:

* **Robert Shiller** (Yale): monthly S&P 500 *price* `P` and *dividend* `D`
  back to 1871 (the same Cowles-Commission lineage Faber's pre-1971 data uses).
  We reconstruct the monthly total-return index as
      TR_t / TR_{t-1} = (P_t + D_t/12) / P_{t-1}
  i.e. price change plus one month's worth of the annualised dividend.

* **Yahoo Finance**: `^GSPC` daily *price* (1927+), `^SP500TR` true daily total
  return (1988+), and `^IRX` 13-week T-bill (1960+).

We produce:

1. ``shiller_monthly_tr()``       -- monthly total-return index, 1871+ (Faber-style).
2. ``long_daily_tr()``            -- a DAILY total-return index from ~1928:
                                     REAL ^SP500TR for 1988+, and for the earlier
                                     era ^GSPC price + Shiller dividend yield.
                                     This lets us apply *true daily* leverage over
                                     ~97 years.
3. ``long_risk_free(...)``        -- a long daily/monthly T-bill series: real ^IRX
                                     from 1960, a documented constant before that.

Everything is cached. The reconstruction is validated against the real
``^SP500TR`` over their overlap (see ``validate_reconstruction``).
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from . import data_loader as dl

SHILLER_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
SHILLER_CACHE = config.RAW_DATA_DIR / "shiller_ie_data.xls"

# Ken French data library: the 1-month US T-bill return (column "RF"), monthly
# from July 1926 (sourced from Ibbotson Associates). This is the standard
# academic risk-free and gives us REAL T-bill rates back past our 1928 daily
# start, so we no longer need a constant placeholder for the pre-1960 era.
FF_URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
          "F-F_Research_Data_Factors_CSV.zip")
FF_CACHE = config.RAW_DATA_DIR / "ff_factors.zip"

# Last-resort constant, only used before the Ken French series begins (1926-07)
# or if the download is unavailable. Our daily history starts in 1928, so this is
# essentially never hit for the daily analysis.
PRE1960_TBILL_ANNUAL = 0.02


# ---------------------------------------------------------------------------
# Shiller monthly data
# ---------------------------------------------------------------------------
def _download_shiller() -> bytes:
    """Download Shiller's ie_data.xls (cached). Returns the raw bytes."""
    if SHILLER_CACHE.exists():
        return SHILLER_CACHE.read_bytes()
    req = urllib.request.Request(SHILLER_URL, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=60).read()
    SHILLER_CACHE.write_bytes(data)
    return data


def _shiller_date_to_timestamp(x: float) -> pd.Timestamp:
    """Convert Shiller's '1871.01' style float to a month-END timestamp."""
    year = int(x)
    month = int(round((x - year) * 100))
    month = min(max(month, 1), 12)
    return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)


def load_shiller() -> pd.DataFrame:
    """Load Shiller monthly data as a DataFrame indexed by month-end date.

    Columns kept: ``P`` (price), ``D`` (annualised dividend), ``GS10`` (long
    rate), plus the reconstructed ``tr_return`` (monthly total return) and
    ``div_yield`` (annualised dividend yield D/P).
    """
    raw = _download_shiller()
    df = pd.read_excel(io.BytesIO(raw), sheet_name="Data", header=7)
    df = df.rename(columns={"Rate GS10": "GS10"})
    df = df[["Date", "P", "D", "GS10"]].copy()
    df = df[pd.to_numeric(df["Date"], errors="coerce").notna()]
    df["Date"] = df["Date"].astype(float)
    df = df[df["P"].notna()]
    df.index = df["Date"].map(_shiller_date_to_timestamp)
    df = df.drop(columns="Date")
    df["P"] = df["P"].astype(float)
    df["D"] = df["D"].astype(float)

    # Monthly total return = price change + one month of the annualised dividend.
    df["div_yield"] = df["D"] / df["P"]
    df["tr_return"] = (df["P"] + df["D"] / 12.0) / df["P"].shift(1) - 1.0
    return df.dropna(subset=["P"])


def shiller_monthly_tr(start: str | None = None) -> pd.Series:
    """Monthly S&P 500 total-return INDEX (rebased to 1.0 at the start)."""
    df = load_shiller()
    r = df["tr_return"].dropna()
    if start is not None:
        r = r[r.index >= pd.Timestamp(start)]
    idx = (1.0 + r).cumprod()
    return idx.rename("shiller_monthly_tr")


def combined_monthly_tr(start: str | None = None,
                        splice: str = "1988-01-01") -> pd.Series:
    """Monthly total-return INDEX from 1871 to the present, kept CURRENT.

    Uses Shiller monthly total return before ``splice`` and the REAL ``^SP500TR``
    monthly total return from ``splice`` onward (Shiller's file lags by a couple
    of years). This is the series used for the Faber-faithful monthly replication.
    """
    shiller_r = load_shiller()["tr_return"].dropna()
    early = shiller_r[shiller_r.index < pd.Timestamp(splice)]

    sp = dl.get_level_series("^SP500TR")
    if sp is not None:
        sp_m = sp.resample("ME").last()
        late = sp_m.pct_change().dropna()
        late = late[late.index >= pd.Timestamp(splice)]
        rets = pd.concat([early, late])
    else:
        rets = early
    rets = rets[~rets.index.duplicated(keep="last")].sort_index()
    if start is not None:
        rets = rets[rets.index >= pd.Timestamp(start)]
    return (1.0 + rets).cumprod().rename("combined_monthly_tr")


# ---------------------------------------------------------------------------
# Long DAILY total-return series (reconstructed pre-1988, real after)
# ---------------------------------------------------------------------------
def long_daily_tr(force: bool = False) -> tuple[pd.Series, dict]:
    """Daily S&P 500 total-return index from ~1928, returned with a provenance dict.

    Construction:
      * 1988-01-04 onward : REAL ``^SP500TR`` daily total return.
      * before 1988       : ``^GSPC`` daily price return + a daily slice of the
                            Shiller monthly dividend yield (annual yield / 252).
      The two pieces are spliced at the first ^SP500TR date so the index is
      continuous (the early piece is scaled to meet the real piece).
    """
    sp500tr = dl.get_level_series("^SP500TR", force=force)
    gspc = dl.get_level_series("^GSPC", force=force)

    if sp500tr is None or gspc is None:
        # Fallback: whatever total return we can get (keeps the pipeline alive).
        s, tk, src = dl.get_underlying_total_return(force=force)
        return s, {"method": "fallback", "source": src, "splice_date": None}

    sp500tr = sp500tr.dropna().sort_index()
    gspc = gspc.dropna().sort_index()
    splice_date = sp500tr.index.min()

    # --- early piece: reconstruct daily TR from ^GSPC price + Shiller dividends ---
    gspc_early = gspc[gspc.index < splice_date]
    price_ret = gspc_early.pct_change()

    shiller = load_shiller()
    # Map each early trading day to that month's annualised dividend yield, then
    # convert to a daily dividend return (geometric split across ~252 days).
    yld = shiller["div_yield"].reindex(
        pd.date_range(shiller.index.min(), gspc_early.index.max(), freq="D")
    ).ffill()
    daily_div = (1.0 + yld) ** (1.0 / config.TRADING_DAYS_PER_YEAR) - 1.0
    daily_div = daily_div.reindex(price_ret.index).ffill().fillna(0.0)

    early_tr_ret = (1.0 + price_ret) * (1.0 + daily_div) - 1.0
    early_tr_ret = early_tr_ret.dropna()

    # --- splice: build one continuous index ---
    # Real piece rebased so it starts at 1.0 on splice_date.
    real_idx = sp500tr / sp500tr.iloc[0]
    # Early piece compounded up to (but not including) splice_date, then scaled so
    # it connects continuously to real_idx at the boundary.
    early_idx = (1.0 + early_tr_ret).cumprod()
    if len(early_idx):
        early_idx = early_idx / early_idx.iloc[-1]  # ends at 1.0 just before splice
        combined = pd.concat([early_idx, real_idx])
    else:
        combined = real_idx
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    combined = combined.rename("long_daily_tr")

    meta = {
        "method": "spliced",
        "splice_date": str(splice_date.date()),
        "start": str(combined.index.min().date()),
        "end": str(combined.index.max().date()),
        "early_source": "^GSPC price + Shiller dividend yield (reconstructed)",
        "modern_source": "^SP500TR (real daily total return)",
        "n_days": int(len(combined)),
    }
    return combined, meta


def validate_reconstruction() -> dict:
    """Compare a reconstructed daily TR (^GSPC + Shiller div) to the REAL
    ^SP500TR over their overlap, to show the reconstruction is sound.

    Returns annualised tracking error and the CAGR of each over the overlap.
    """
    sp500tr = dl.get_level_series("^SP500TR")
    gspc = dl.get_level_series("^GSPC")
    if sp500tr is None or gspc is None:
        return {}
    from .returns import simple_returns
    shiller = load_shiller()

    overlap_start = max(sp500tr.index.min(), gspc.index.min())
    real = sp500tr[sp500tr.index >= overlap_start]
    g = gspc[gspc.index >= overlap_start]
    pr = g.pct_change()
    yld = shiller["div_yield"].reindex(
        pd.date_range(shiller.index.min(), g.index.max(), freq="D")).ffill()
    dd = ((1.0 + yld) ** (1.0 / config.TRADING_DAYS_PER_YEAR) - 1.0)
    dd = dd.reindex(pr.index).ffill().fillna(0.0)
    recon_ret = ((1.0 + pr) * (1.0 + dd) - 1.0).dropna()
    real_ret = simple_returns(real)

    common = recon_ret.index.intersection(real_ret.index)
    a = recon_ret.reindex(common)
    b = real_ret.reindex(common)
    diff = a - b
    td = config.TRADING_DAYS_PER_YEAR
    return {
        "overlap_start": str(common.min().date()),
        "overlap_end": str(common.max().date()),
        "n_days": len(common),
        "tracking_error_ann": float(diff.std(ddof=1) * np.sqrt(td)),
        "recon_cagr": float((1 + a).prod() ** (td / len(a)) - 1),
        "real_cagr": float((1 + b).prod() ** (td / len(b)) - 1),
        "correlation": float(a.corr(b)),
    }


# ---------------------------------------------------------------------------
# Ken French 1-month T-bill (real risk-free back to 1926)
# ---------------------------------------------------------------------------
def load_ff_riskfree() -> pd.Series:
    """Monthly 1-month T-bill RETURN (decimal), month-end indexed, from 1926-07.

    Parsed from the Ken French ``F-F_Research_Data_Factors`` file (RF column,
    quoted in percent-per-month). Returns an empty Series if unavailable.
    """
    import io
    import re
    import zipfile

    try:
        if FF_CACHE.exists():
            data = FF_CACHE.read_bytes()
        else:
            req = urllib.request.Request(FF_URL, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=60).read()
            FF_CACHE.write_bytes(data)
        z = zipfile.ZipFile(io.BytesIO(data))
        txt = z.read(z.namelist()[0]).decode("latin-1")
    except Exception:
        return pd.Series(dtype=float)

    rows = {}
    for line in txt.splitlines():
        line = line.strip()
        if not re.match(r"^\d{6}\s*,", line):   # monthly rows are 'YYYYMM,...'
            continue
        parts = [p.strip() for p in line.split(",")]
        ym = parts[0]
        try:
            rf = float(parts[4]) / 100.0        # RF is the 5th column, percent/month
        except (IndexError, ValueError):
            continue
        y, mo = int(ym[:4]), int(ym[4:6])
        if 1 <= mo <= 12:
            ts = pd.Timestamp(year=y, month=mo, day=1) + pd.offsets.MonthEnd(0)
            rows[ts] = rf
    return pd.Series(rows).sort_index().rename("ff_rf_monthly")


# ---------------------------------------------------------------------------
# Long risk-free (T-bill) series
# ---------------------------------------------------------------------------
def avg_real_tbill_monthly() -> float:
    """The AVERAGE monthly T-bill return over the real data we have (Ken French,
    1926+). Used only to fill the pre-1926 gap, so a missing stretch is an average
    of real history rather than an arbitrary made-up number."""
    ff = load_ff_riskfree()
    if len(ff):
        return float(ff.mean())
    return (1.0 + PRE1960_TBILL_ANNUAL) ** (1.0 / 12.0) - 1.0


def long_risk_free_daily(index: pd.Index) -> pd.Series:
    """Daily risk-free return aligned to ``index``, using REAL T-bill rates:

      * 1960 onward : ^IRX (13-week T-bill), converted to a daily rate.
      * before 1960 : Ken French 1-month T-bill (Ibbotson), the monthly return
                      spread evenly across that month's trading days.
      * before 1926 : the AVERAGE of the real T-bill series above (the daily
                      history starts in 1928, so this is essentially never hit).
    """
    rf = dl.get_risk_free_daily(index).copy()    # ^IRX-based, 0 before it starts
    irx = dl.get_level_series(config.RISK_FREE_TICKER)
    irx_start = irx.index.min() if irx is not None else pd.Timestamp("1960-01-01")
    # Fill value for any gap = the average of the REAL series (not a constant).
    fill_daily = (1.0 + avg_real_tbill_monthly()) ** (1.0 / config.TRADING_DAYS_PER_MONTH) - 1.0

    pre = index[index < irx_start]
    if len(pre):
        ff = load_ff_riskfree()
        if len(ff):
            ff_p = pd.Series(ff.values, index=ff.index.to_period("M"))
            pm = pre.to_period("M")
            # number of in-sample trading days per pre-1960 month
            days = pd.Series(1, index=pm).groupby(level=0).transform("sum")
            monthly = pd.Series(ff_p.reindex(pm).values, index=pre)
            rf.loc[pre] = monthly.values / days.values
        rf.loc[pre] = rf.loc[pre].fillna(fill_daily)   # pre-1926 gap -> real-series average
    return rf.rename("rf_daily")


def long_risk_free_monthly(index: pd.Index) -> pd.Series:
    """Monthly risk-free return aligned to month-end ``index``: ^IRX (1960+),
    Ken French 1-month T-bill (1926-1960), and — for the pre-1926 gap that only
    the 1901-1926 monthly replication touches — the AVERAGE of the real series."""
    irx = dl.get_level_series(config.RISK_FREE_TICKER)
    out = pd.Series(np.nan, index=index)

    ff = load_ff_riskfree()
    if len(ff):
        out = ff.reindex(index)               # real monthly T-bill where available
    if irx is not None:
        annual = (irx / 100.0).clip(lower=-0.99)
        irx_m = ((1.0 + annual) ** (1.0 / 12.0) - 1.0).resample("ME").last()
        irx_m = irx_m.reindex(index).ffill()
        mask = index >= irx.index.min()        # ^IRX takes over from 1960
        out[mask] = irx_m[mask]
    return out.fillna(avg_real_tbill_monthly()).rename("rf_monthly")
