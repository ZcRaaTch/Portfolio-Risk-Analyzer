"""
config.py
---------
Every assumption of the project lives in this one file, so that anyone
reviewing the work (or an interviewer) can see exactly what was assumed.
Change a value here and re-run `python main.py`; nothing else needs editing.
"""

from datetime import date

# ---------------------------------------------------------------------------
# 1. Portfolio universe
# ---------------------------------------------------------------------------
# Yahoo Finance tickers for NSE-listed shares end in ".NS".
# The dictionary keeps the ticker -> readable name mapping in one place.
STOCKS = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "TCS",
    "HDFCBANK.NS": "HDFC Bank",
    "INFY.NS": "Infosys",
    "ICICIBANK.NS": "ICICI Bank",
}

# Broad sector of each holding. Used only to describe concentration,
# not in any calculation.
SECTORS = {
    "Reliance Industries": "Energy & Conglomerate",
    "TCS": "Information Technology",
    "HDFC Bank": "Banking",
    "Infosys": "Information Technology",
    "ICICI Bank": "Banking",
}

# Equal weights: 20% in each stock. Weights must add up to 1.
WEIGHTS = {name: 0.20 for name in STOCKS.values()}

# Benchmark used to judge the portfolio against "the market".
# ^NSEI is the NIFTY 50 index on Yahoo Finance.
BENCHMARK_TICKER = "^NSEI"
BENCHMARK_NAME = "NIFTY 50"

# ---------------------------------------------------------------------------
# 2. Time period
# ---------------------------------------------------------------------------
# The analysis uses the most recent LOOKBACK_YEARS of daily data, ending on
# END_DATE. Set END_DATE to a fixed date such as date(2026, 9, 30) if you
# want the results to stay identical every time you run the project.
LOOKBACK_YEARS = 2
END_DATE = None  # None means "today"

# ---------------------------------------------------------------------------
# 3. Risk-free rate (needed only for the Sharpe Ratio)
# ---------------------------------------------------------------------------
# Proxy: yield of India's 91-day Treasury Bill, the standard short-term
# risk-free instrument for INR investors.
# Value: 5.26% p.a., the cut-off yield (YTM 5.2599%) at the RBI auction
# reported on 2 September 2026.
# Source: Aditya Birla Sun Life MF, Daily Fixed Income Tracker, 03 Sep 2026
# https://mutualfund.adityabirlacapital.com/-/media/knowledgecenter/pdf/daily-fixed-income-tracker-03-sep-2026.pdf
# Note: T-bill yields were higher earlier in the period, so a single recent
# value is a simplification. The report shows how the Sharpe Ratio changes
# for other risk-free rates (see RF_SENSITIVITY) so the conclusion does not
# hinge on this one number. Update this value if you run the project later.
RISK_FREE_RATE = 0.0526
RISK_FREE_SOURCE_URL = (
    "https://mutualfund.adityabirlacapital.com/-/media/knowledgecenter/pdf/"
    "daily-fixed-income-tracker-03-sep-2026.pdf"
)
RISK_FREE_LABEL = "91-day T-Bill cut-off yield, RBI auction of 2 Sep 2026"
RF_SENSITIVITY = [0.0, 0.05, 0.06, 0.07]

# ---------------------------------------------------------------------------
# 4. Conventions
# ---------------------------------------------------------------------------
# Market convention for the number of trading days in a year, used to scale
# daily figures to annual ones.
TRADING_DAYS = 252

# Data cleaning: a stock with a short gap (e.g. a missing quote) keeps its
# previous price for at most this many days. Longer gaps are dropped instead.
MAX_FFILL_DAYS = 2

# ---------------------------------------------------------------------------
# 5. Folders
# ---------------------------------------------------------------------------
DATA_DIR = "data"
OUTPUT_DIR = "outputs"
CHART_DIR = "outputs/charts"
PRICES_FILE = "data/prices_raw.csv"


def resolve_dates():
    """Return (start_date, end_date) as date objects for the analysis window."""
    end = END_DATE or date.today()
    try:
        start = end.replace(year=end.year - LOOKBACK_YEARS)
    except ValueError:  # 29 February in a leap year
        start = end.replace(year=end.year - LOOKBACK_YEARS, day=28)
    return start, end

# ---------------------------------------------------------------------------
# 6. Report details
# ---------------------------------------------------------------------------
REPORT_TITLE = "Portfolio Performance & Risk Analyzer"
REPORT_AUTHOR = "Abhinav Awana | MBA, Department of Management Studies, IIT Roorkee"
