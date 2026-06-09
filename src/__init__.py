"""
Leveraged Trend-Following research package.

A small, readable toolkit for testing whether rotating into daily-leveraged
S&P 500 exposure during below-trend ("bad") markets can improve long-term
returns, versus buy-and-hold and the classic moving-average-to-cash rule.

Modules
-------
config         project paths, parameters, tickers, cost assumptions
data_loader    download + cache market data (with a synthetic fallback)
data_cleaning  clean/align series and build the data-summary table
returns        prices -> returns -> cumulative index helpers
signals        moving-average trend signal (lagged to avoid look-ahead)
backtest       from-scratch daily backtester (buy-hold, MA-to-cash, leveraged)
metrics        CAGR, vol, Sharpe, Sortino, drawdown, Calmar, etc.
sweep          parameter sweep + period/episode analysis
plots          all charts, saved to charts/
monte_carlo    volatility-decay / optimal-leverage simulations
etf_tests      synthetic leverage vs real leveraged ETFs
"""

__version__ = "1.0.0"
