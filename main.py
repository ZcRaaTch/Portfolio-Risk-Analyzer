"""
main.py
-------
Runs the whole Portfolio Performance & Risk Analyzer in one go:

    1. download (or load) daily prices
    2. clean the data
    3. compute returns, portfolio metrics, correlation and risk contribution
    4. draw the charts
    5. write CSV tables, the PDF report and the resume/interview notes

Usage
    python main.py                  # download the latest 2 years and analyse
    python main.py --offline        # re-use data/prices_raw.csv (no internet)
    python main.py --end 2026-09-30 # fix the end date for reproducible results
    python main.py --rf 0.065       # try a different risk-free rate
"""

import argparse
import os
from datetime import date

import config
from analytics import (PORTFOLIO_NAME, fetch_prices, load_download_info, load_prices,
                       run_analysis, save_tables)
from charts import make_all_charts
from insights import build_findings, readme_results, resume_and_pitch
from report import build_pdf


def parse_args():
    p = argparse.ArgumentParser(description="Portfolio Performance & Risk Analyzer")
    p.add_argument("--offline", action="store_true",
                   help=f"load prices from {config.PRICES_FILE} instead of downloading")
    p.add_argument("--csv", help="load prices from this CSV file (Date column + one "
                                 "column per stock name and benchmark)")
    p.add_argument("--end", help="end date YYYY-MM-DD (default: today)")
    p.add_argument("--rf", type=float, default=config.RISK_FREE_RATE,
                   help="annual risk-free rate as a decimal, e.g. 0.0526")
    return p.parse_args()


def update_readme(res, path="README.md"):
    """Replace the README's Sample results section with this run's numbers."""
    start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    if not os.path.exists(path):
        return
    text = open(path, encoding="utf-8").read()
    if start in text and end in text:
        before, rest = text.split(start, 1)
        after = rest.split(end, 1)[1]
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{before}{start}\n{readme_results(res)}\n{end}{after}")
        print("Updated the Sample results section of README.md")


def main():
    args = parse_args()
    for folder in (config.DATA_DIR, config.OUTPUT_DIR, config.CHART_DIR):
        os.makedirs(folder, exist_ok=True)

    # 1. Data --------------------------------------------------------------
    if args.end:
        config.END_DATE = date.fromisoformat(args.end)
    start, end = config.resolve_dates()

    if args.csv:
        print(f"Loading prices from {args.csv}")
        prices, info = load_prices(args.csv), {}
    elif args.offline:
        print(f"Loading saved prices from {config.PRICES_FILE}")
        prices, info = load_prices(), load_download_info()
    else:
        print(f"Downloading daily prices from Yahoo Finance: {start} to {end}")
        prices = fetch_prices(start, end)
        info = load_download_info()
        print(f"Saved raw prices to {config.PRICES_FILE}")

    # 2-3. Cleaning and analysis -------------------------------------------
    res = run_analysis(prices, rf_annual=args.rf)
    save_tables(res)
    print(f"Analysed {res['period']['trading_days']} daily returns "
          f"({res['period']['start']} to {res['period']['end']})")

    # 4. Charts --------------------------------------------------------------
    charts = make_all_charts(res)
    print(f"Saved {len(charts)} charts to {config.CHART_DIR}/")

    # 5. Report and notes ----------------------------------------------------
    pdf_path = os.path.join(config.OUTPUT_DIR, "Portfolio_Risk_Report.pdf")
    build_pdf(res, charts, pdf_path, info)
    notes_path = os.path.join(config.OUTPUT_DIR, "resume_and_talking_points.md")
    with open(notes_path, "w") as f:
        f.write(resume_and_pitch(res))
    update_readme(res)
    print(f"Saved report to {pdf_path}")
    print(f"Saved resume bullets and interview answers to {notes_path}")

    # Console summary -------------------------------------------------------
    table = res["summary"].copy()
    pct_cols = [c for c in table.columns if c not in ("Sharpe ratio", "Beta vs benchmark")]
    table[pct_cols] = table[pct_cols].map(lambda x: f"{x:.1%}")
    table[["Sharpe ratio", "Beta vs benchmark"]] = (
        table[["Sharpe ratio", "Beta vs benchmark"]].map(lambda x: f"{x:.2f}"))
    print("\nSUMMARY METRICS")
    print(table.to_string())
    print(f"\nRisk-free rate used: {args.rf:.2%}")
    print("\nKEY FINDINGS")
    for i, (title, text) in enumerate(build_findings(res), 1):
        print(f"{i}. {title}: {text}")
    print(f"\nDone. Open {pdf_path} to see the report "
          f"({PORTFOLIO_NAME} vs {config.BENCHMARK_NAME}).")


if __name__ == "__main__":
    main()
