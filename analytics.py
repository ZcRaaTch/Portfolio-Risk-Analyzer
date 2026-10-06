"""
analytics.py
------------
All data handling and financial calculations for the
Portfolio Performance & Risk Analyzer.

The functions are deliberately small. Each one does a single job and can be
explained in one or two sentences, which is the point: every number in the
report can be traced back to a short, readable formula in this file.

Conventions used throughout
* Prices are adjusted closing prices (adjusted for dividends and splits).
* Returns are simple daily returns: r_t = P_t / P_(t-1) - 1.
* "Annualised" figures scale daily figures with TRADING_DAYS (252).
"""

import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import config

PORTFOLIO_NAME = "Equal-Weight Portfolio"


# =============================================================================
# 1. LOADING DATA
# =============================================================================
def fetch_prices(start, end, save_path=config.PRICES_FILE):
    """
    Download daily adjusted closing prices from Yahoo Finance.

    Parameters
    ----------
    start, end : datetime.date
        Analysis window. Yahoo treats `end` as exclusive, so one day is added
        to make sure the last trading day is included.
    save_path : str
        Where the raw downloaded prices are saved, so the analysis can be
        re-run later on exactly the same data (python main.py --offline).

    Returns
    -------
    pandas.DataFrame
        One column per stock (readable names) plus the benchmark,
        indexed by trading date.
    """
    import yfinance as yf  # imported here so offline runs do not need it

    tickers = list(config.STOCKS) + [config.BENCHMARK_TICKER]
    raw = yf.download(
        tickers,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=True,  # "Close" is then adjusted for dividends and splits
        progress=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError(
            "Yahoo Finance returned no data. Check your internet connection "
            "and try again in a few minutes."
        )

    # With several tickers yfinance returns columns like ("Close", "TCS.NS").
    prices = raw["Close"].copy()
    names = dict(config.STOCKS)
    names[config.BENCHMARK_TICKER] = config.BENCHMARK_NAME
    prices = prices.rename(columns=names)

    # Fail loudly if a stock could not be downloaded at all.
    stock_names = list(config.STOCKS.values())
    empty = [c for c in stock_names if c not in prices or prices[c].isna().all()]
    if empty:
        raise RuntimeError(f"No price data downloaded for: {empty}")

    # The benchmark is useful but not essential: drop it if it failed.
    if prices[config.BENCHMARK_NAME].isna().all():
        print(f"WARNING: {config.BENCHMARK_NAME} could not be downloaded; "
              "continuing without a benchmark.")
        prices = prices.drop(columns=config.BENCHMARK_NAME)

    prices = prices[[c for c in stock_names + [config.BENCHMARK_NAME] if c in prices]]
    prices.index.name = "Date"
    prices.to_csv(save_path)

    # Record when and how the data was obtained (evidence of authenticity).
    info = {
        "source": "Yahoo Finance via the yfinance Python package",
        "yfinance_version": yf.__version__,
        "tickers": tickers,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        "price_field": "Close with auto_adjust=True (dividend and split adjusted)",
    }
    with open(save_path.replace(".csv", "_info.json"), "w") as f:
        json.dump(info, f, indent=2)
    return prices


def load_prices(path=config.PRICES_FILE):
    """Load previously downloaded prices from CSV (used for offline runs)."""
    prices = pd.read_csv(path, index_col="Date", parse_dates=True)
    return prices


def load_download_info(path=config.PRICES_FILE):
    """Return the metadata saved next to the price file, if it exists."""
    try:
        with open(path.replace(".csv", "_info.json")) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# =============================================================================
# 2. CLEANING
# =============================================================================
def clean_prices(prices, max_ffill=config.MAX_FFILL_DAYS):
    """
    Clean a price table and report what was changed.

    Steps
    1. Sort by date and remove duplicate dates.
    2. Remove timezone information (daily data does not need it).
    3. Drop dates on which no security has a price (e.g. exchange holidays).
    4. Fill short gaps (at most `max_ffill` days) with the last known price.
       Economically this means "no trade, so no price change that day".
    5. Drop any date that still has a missing price, so every security is
       measured over exactly the same days.
    6. Check that every price is positive.

    Returns
    -------
    (clean_prices, log) where log is a dict describing each step.
    """
    log = {"rows_raw": int(len(prices))}
    df = prices.sort_index()

    dupes = int(df.index.duplicated().sum())
    df = df[~df.index.duplicated(keep="last")]
    log["duplicate_dates_removed"] = dupes

    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)

    before = len(df)
    df = df.dropna(how="all")
    log["empty_dates_removed"] = int(before - len(df))

    log["missing_values_before_fill"] = {c: int(v) for c, v in df.isna().sum().items()}
    filled = df.ffill(limit=max_ffill)
    log["values_forward_filled"] = int(df.isna().sum().sum() - filled.isna().sum().sum())

    before = len(filled)
    df = filled.dropna(how="any")
    log["incomplete_dates_removed"] = int(before - len(df))

    if (df <= 0).any().any():
        raise ValueError("Found zero or negative prices; the data is corrupt.")

    log["rows_clean"] = int(len(df))
    log["first_date"] = df.index[0].date().isoformat()
    log["last_date"] = df.index[-1].date().isoformat()
    return df, log


# =============================================================================
# 3. RETURNS AND PORTFOLIO CONSTRUCTION
# =============================================================================
def daily_returns(prices):
    """Simple daily returns: today's price / yesterday's price - 1."""
    return prices.pct_change().iloc[1:]


def portfolio_returns(stock_returns, weights):
    """
    Daily return of a constant-weight portfolio.

    Each day the portfolio return is the weighted average of the stock
    returns: r_p = sum(w_i * r_i). Holding the weights fixed every day
    implicitly assumes the portfolio is rebalanced back to 20% each day
    (no transaction costs). The buy-and-hold alternative is computed
    separately in `buy_and_hold_value` for comparison.
    """
    w = pd.Series(weights)[stock_returns.columns]
    return (stock_returns * w).sum(axis=1).rename(PORTFOLIO_NAME)


def buy_and_hold_value(stock_prices, weights):
    """
    Value of Rs 1 invested on day one at 20% per stock and never rebalanced.
    Weights then drift with prices; this is what an investor who simply
    bought and held would actually experience.
    """
    w = pd.Series(weights)[stock_prices.columns]
    growth = stock_prices / stock_prices.iloc[0]
    return (growth * w).sum(axis=1)


def wealth_index(returns, base_date):
    """
    Growth of Rs 1 from compounding daily returns, starting at 1.0 on
    `base_date` (the first price date, the day before the first return).
    Works for a Series or a DataFrame.
    """
    wealth = (1 + returns).cumprod()
    if isinstance(returns, pd.DataFrame):
        first = pd.DataFrame([[1.0] * returns.shape[1]], columns=returns.columns,
                             index=[base_date])
    else:
        first = pd.Series([1.0], index=[base_date], name=returns.name)
    out = pd.concat([first, wealth])
    out.index.name = "Date"
    return out


# =============================================================================
# 4. PERFORMANCE AND RISK METRICS (for one return series)
# =============================================================================
def total_return(r):
    """Cumulative return over the whole period: product of (1 + r) minus 1."""
    return float((1 + r).prod() - 1)


def annualised_return(r, periods=config.TRADING_DAYS):
    """
    Compound annual growth rate (CAGR): the constant yearly return that
    would turn the starting value into the ending value.
    CAGR = (1 + total return) ^ (252 / number of days) - 1
    """
    return float((1 + total_return(r)) ** (periods / len(r)) - 1)


def annualised_mean_return(r, periods=config.TRADING_DAYS):
    """Arithmetic average daily return x 252 (used in Sharpe and attribution)."""
    return float(r.mean() * periods)


def annualised_volatility(r, periods=config.TRADING_DAYS):
    """
    Standard deviation of daily returns scaled to a year.
    Volatility grows with the square root of time, hence sqrt(252).
    """
    return float(r.std() * np.sqrt(periods))


def daily_risk_free(rf_annual, periods=config.TRADING_DAYS):
    """Convert an annual risk-free rate into an equivalent daily rate."""
    return (1 + rf_annual) ** (1 / periods) - 1


def sharpe_ratio(r, rf_annual=config.RISK_FREE_RATE, periods=config.TRADING_DAYS):
    """
    Return earned per unit of risk, above the risk-free rate.
    Sharpe = mean(daily excess return) / std(daily return) x sqrt(252)
    """
    excess = r - daily_risk_free(rf_annual, periods)
    return float(excess.mean() / r.std() * np.sqrt(periods))


def drawdown_series(wealth):
    """Percentage fall of the wealth index from its highest level so far."""
    return wealth / wealth.cummax() - 1


def max_drawdown(wealth):
    """
    Largest peak-to-trough fall of the wealth index.

    Returns a dict with the drawdown (a negative number), the peak date,
    the trough date, and the recovery date (None if the previous peak has
    not been regained by the end of the period).
    """
    dd = drawdown_series(wealth)
    trough = dd.idxmin()
    peak = wealth.loc[:trough].idxmax()
    after = wealth.loc[trough:]
    recovered = after[after >= wealth.loc[peak]]
    recovery = recovered.index[0] if len(recovered) else None
    return {
        "max_drawdown": float(dd.min()),
        "peak_date": peak.date().isoformat(),
        "trough_date": trough.date().isoformat(),
        "recovery_date": recovery.date().isoformat() if recovery is not None else None,
        "days_peak_to_trough": int(wealth.loc[peak:trough].shape[0] - 1),
    }


def beta(r, market_r):
    """Sensitivity to the market: cov(r, market) / var(market)."""
    aligned = pd.concat([r, market_r], axis=1).dropna()
    cov = aligned.cov().iloc[0, 1]
    return float(cov / aligned.iloc[:, 1].var())


# =============================================================================
# 5. DIVERSIFICATION AND RISK CONTRIBUTION
# =============================================================================
def diversification_stats(stock_returns, weights, periods=config.TRADING_DAYS):
    """
    How much risk the portfolio avoids by holding several stocks.

    * weighted_avg_vol: what portfolio volatility would be if the stocks
      were perfectly correlated (no diversification at all).
    * portfolio_vol:    actual volatility, sqrt(w' * Cov * w).
    * diversification_ratio = weighted_avg_vol / portfolio_vol (1.0 = none).
    * volatility_reduction  = 1 - portfolio_vol / weighted_avg_vol.
    """
    w = pd.Series(weights)[stock_returns.columns].values
    cov = stock_returns.cov().values * periods
    vols = stock_returns.std().values * np.sqrt(periods)
    port_vol = float(np.sqrt(w @ cov @ w))
    weighted_avg_vol = float(w @ vols)

    corr = stock_returns.corr()
    upper = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
    return {
        "portfolio_vol": port_vol,
        "weighted_avg_vol": weighted_avg_vol,
        "diversification_ratio": weighted_avg_vol / port_vol,
        "volatility_reduction": 1 - port_vol / weighted_avg_vol,
        "avg_pairwise_corr": float(upper.mean()),
        "max_corr_pair": [*upper.idxmax(), float(upper.max())],
        "min_corr_pair": [*upper.idxmin(), float(upper.min())],
    }


def risk_contribution(stock_returns, weights, periods=config.TRADING_DAYS):
    """
    Split portfolio volatility into the part each stock is responsible for.

    marginal contribution  MRC_i = (Cov * w)_i / sigma_p
    component contribution CRC_i = w_i * MRC_i   (these add up to sigma_p)
    share of risk               = CRC_i / sigma_p (these add up to 100%)

    A stock whose share of risk is larger than its weight is making the
    portfolio riskier than its capital allocation suggests.
    """
    w = pd.Series(weights)[stock_returns.columns]
    cov = stock_returns.cov() * periods
    port_vol = float(np.sqrt(w @ cov @ w))
    mrc = cov @ w / port_vol
    crc = w * mrc
    out = pd.DataFrame({
        "Weight": w,
        "Marginal contribution": mrc,
        "Volatility contribution": crc,
        "Share of portfolio risk": crc / port_vol,
    })
    # Return attribution: with constant weights the portfolio's average
    # return is exactly the weighted sum of the stocks' average returns.
    out["Return contribution"] = w * stock_returns.mean() * periods
    out["Risk share minus weight"] = out["Share of portfolio risk"] - out["Weight"]
    return out


# =============================================================================
# 6. PUTTING IT TOGETHER
# =============================================================================
def summarise(returns_by_asset, wealth_by_asset, market_r=None,
              rf_annual=config.RISK_FREE_RATE):
    """Build the metrics table: one row per asset, one column per metric."""
    rows = {}
    for name, r in returns_by_asset.items():
        mdd = max_drawdown(wealth_by_asset[name])
        rows[name] = {
            "Cumulative return": total_return(r),
            "Annualised return (CAGR)": annualised_return(r),
            "Annualised volatility": annualised_volatility(r),
            "Sharpe ratio": sharpe_ratio(r, rf_annual),
            "Max drawdown": mdd["max_drawdown"],
            "Beta vs benchmark": beta(r, market_r) if market_r is not None else np.nan,
        }
    return pd.DataFrame(rows).T


def run_analysis(raw_prices, weights=None, rf_annual=config.RISK_FREE_RATE):
    """
    Run the complete analysis on a raw price table and return every result
    in one dictionary (used by main.py, the notebook and the report).
    """
    weights = weights or config.WEIGHTS
    stock_names = list(weights)
    if abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError("Portfolio weights must add up to 1.")

    prices, clean_log = clean_prices(raw_prices)
    has_bench = config.BENCHMARK_NAME in prices.columns
    stock_prices = prices[stock_names]

    stock_r = daily_returns(stock_prices)
    port_r = portfolio_returns(stock_r, weights)
    bench_r = daily_returns(prices[config.BENCHMARK_NAME]) if has_bench else None

    # Returns of everything we report on, in display order.
    all_r = {name: stock_r[name] for name in stock_names}
    all_r[PORTFOLIO_NAME] = port_r
    if has_bench:
        all_r[config.BENCHMARK_NAME] = bench_r

    base_date = prices.index[0]
    wealth = pd.DataFrame({k: wealth_index(v, base_date) for k, v in all_r.items()})
    drawdowns = drawdown_series(wealth)

    summary = summarise(all_r, wealth, bench_r, rf_annual)

    bh_value = buy_and_hold_value(stock_prices, weights)
    bh_r = daily_returns(bh_value)
    buy_hold = {
        "Cumulative return": float(bh_value.iloc[-1] - 1),
        "Annualised return (CAGR)": annualised_return(bh_r),
        "Annualised volatility": annualised_volatility(bh_r),
        "Max drawdown": max_drawdown(bh_value)["max_drawdown"],
        "final_weights": (stock_prices.iloc[-1] / stock_prices.iloc[0]
                          * pd.Series(weights) / bh_value.iloc[-1]).to_dict(),
    }

    sensitivity = pd.DataFrame(
        {f"{rf:.0%}": {k: sharpe_ratio(v, rf) for k, v in all_r.items()}
         for rf in config.RF_SENSITIVITY}
    )

    sector_weights = (pd.Series(weights)
                      .groupby(pd.Series(config.SECTORS)).sum()
                      .sort_values(ascending=False))

    n_days = len(port_r)
    years = (prices.index[-1] - prices.index[0]).days / 365.25
    return {
        "prices": prices,
        "clean_log": clean_log,
        "stock_returns": stock_r,
        "portfolio_returns": port_r,
        "benchmark_returns": bench_r,
        "wealth": wealth,
        "drawdowns": drawdowns,
        "summary": summary,
        "portfolio_mdd": max_drawdown(wealth[PORTFOLIO_NAME]),
        "benchmark_mdd": max_drawdown(wealth[config.BENCHMARK_NAME]) if has_bench else None,
        "correlation": stock_r.corr(),
        "diversification": diversification_stats(stock_r, weights),
        "risk_contribution": risk_contribution(stock_r, weights),
        "buy_and_hold": buy_hold,
        "sharpe_sensitivity": sensitivity,
        "sector_weights": sector_weights,
        "weights": pd.Series(weights),
        "has_benchmark": has_bench,
        "rf_annual": rf_annual,
        "period": {
            "start": prices.index[0].date().isoformat(),
            "end": prices.index[-1].date().isoformat(),
            "trading_days": n_days,
            "calendar_years": years,
            "observed_days_per_year": n_days / years,
        },
    }


def save_tables(results, out_dir=config.OUTPUT_DIR):
    """Write the main result tables to CSV so they can be inspected in Excel."""
    results["prices"].to_csv(f"{out_dir}/prices_clean.csv")
    results["stock_returns"].assign(
        **{PORTFOLIO_NAME: results["portfolio_returns"]}
    ).to_csv(f"{out_dir}/daily_returns.csv")
    results["summary"].to_csv(f"{out_dir}/summary_metrics.csv")
    results["correlation"].to_csv(f"{out_dir}/correlation_matrix.csv")
    results["risk_contribution"].to_csv(f"{out_dir}/risk_contribution.csv")
    results["sharpe_sensitivity"].to_csv(f"{out_dir}/sharpe_sensitivity.csv")

    extra = {
        "period": results["period"],
        "cleaning": results["clean_log"],
        "risk_free_rate": results["rf_annual"],
        "diversification": results["diversification"],
        "portfolio_max_drawdown": results["portfolio_mdd"],
        "benchmark_max_drawdown": results["benchmark_mdd"],
        "buy_and_hold": results["buy_and_hold"],
        "sector_weights": results["sector_weights"].to_dict(),
    }
    with open(f"{out_dir}/results.json", "w") as f:
        json.dump(extra, f, indent=2, default=str)
