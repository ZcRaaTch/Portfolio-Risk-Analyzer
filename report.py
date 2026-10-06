"""
report.py
---------
Builds the PDF project report (and a Markdown file of talking points)
directly from the computed results. No figure in the report is typed by
hand; everything is read from the results dictionary, so the report always
matches the data it was generated from.
"""

from datetime import date
from urllib.parse import quote
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem,
                                Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

import config
from analytics import PORTFOLIO_NAME
from insights import (build_findings, business_interpretation, conclusion,
                      fmt_date, key_numbers, limitations, pct)

NAVY = colors.HexColor("#0d366b")
BLUE = colors.HexColor("#2a78d6")
INK = colors.HexColor("#1f1f1d")
INK_2 = colors.HexColor("#52514e")
TINT = colors.HexColor("#f4f3f0")
RULE = colors.HexColor("#d9d8d2")

PAGE_W, PAGE_H = A4
MARGIN = 0.75 * inch
CONTENT_W = PAGE_W - 2 * MARGIN


# -----------------------------------------------------------------------------
# Styles
# -----------------------------------------------------------------------------
def _styles():
    base = getSampleStyleSheet()
    s = {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=21, leading=25, textColor=NAVY, alignment=0,
                                spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10.5,
                                   leading=14, textColor=INK_2, spaceAfter=2),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.5, leading=11,
                               textColor=INK_2),
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                             textColor=NAVY, spaceBefore=10, spaceAfter=5),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, leading=13,
                             textColor=INK, spaceBefore=6, spaceAfter=3),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.3, leading=13,
                               textColor=INK, spaceAfter=5),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.8, leading=10,
                                textColor=INK_2),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.3, leading=10.5,
                               textColor=INK),
        "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.3,
                                leading=10.5, textColor=INK),
        "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8.3,
                               leading=10.5, textColor=colors.white),
        "kpi": ParagraphStyle("kpi", fontName="Helvetica-Bold", fontSize=16, leading=19,
                              textColor=NAVY, alignment=TA_CENTER),
        "kpil": ParagraphStyle("kpil", fontName="Helvetica", fontSize=7.6, leading=9.5,
                               textColor=INK_2, alignment=TA_CENTER),
        "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique", fontSize=7.8,
                                  leading=10, textColor=INK_2, spaceAfter=8),
    }
    return s


def _table(rows, col_widths, st, bold_rows=(), align_right_from=1):
    """A clean data table: navy header, light zebra rows, numbers right-aligned."""
    data = []
    for i, row in enumerate(rows):
        style = st["head"] if i == 0 else (st["cellb"] if i in bold_rows else st["cell"])
        right = ParagraphStyle(style.name + "_r", parent=style, alignment=2)
        # Numeric columns (from align_right_from onwards) are right-aligned.
        data.append([Paragraph(str(c), right if j >= align_right_from else style)
                     for j, c in enumerate(row)])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), TINT))
    t.setStyle(TableStyle(cmds))
    return t


def _image(path, width=CONTENT_W):
    """Insert a chart scaled to `width` while keeping its proportions."""
    iw, ih = ImageReader(path).getSize()
    return Image(path, width=width, height=width * ih / iw)


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 0.6 * inch, PAGE_W - MARGIN, 0.6 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(INK_2)
    canvas.drawString(MARGIN, 0.45 * inch,
                      f"{config.REPORT_TITLE}  |  Data: Yahoo Finance  |  "
                      "Academic project, not investment advice")
    canvas.drawRightString(PAGE_W - MARGIN, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------
def build_pdf(res, chart_paths, path, download_info=None):
    st = _styles()
    k = key_numbers(res)
    s = res["summary"]
    download_info = download_info or {}
    story = []
    P = lambda text, style="body": Paragraph(text, st[style])  # noqa: E731

    # ---------------- Title block ----------------
    story += [
        P(escape(config.REPORT_TITLE), "title"),
        P("Historical performance and risk analysis of an equal-weight portfolio of "
          "five NSE large-cap stocks", "subtitle"),
        P(f"{config.REPORT_AUTHOR}<br/>Data period: {k['start']} to {k['end']} "
          f"({k['days']} trading days)  |  Report generated: "
          f"{fmt_date(date.today().isoformat())}", "meta"),
        Spacer(1, 10),
    ]

    # KPI strip: the five headline portfolio numbers.
    kpis = [
        (pct(k["cum"]), "Cumulative return"),
        (pct(k["cagr"]), "Annualised return (CAGR)"),
        (pct(k["vol"]), "Annualised volatility"),
        (f"{k['sharpe']:.2f}", f"Sharpe Ratio (rf {pct(k['rf'], 2)})"),
        (pct(k["mdd"]), "Maximum drawdown"),
    ]
    strip = Table([[P(v, "kpi") for v, _ in kpis], [P(l, "kpil") for _, l in kpis]],
                  colWidths=[CONTENT_W / 5] * 5)
    strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TINT),
        ("LINEABOVE", (0, 0), (-1, 0), 2, NAVY),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
    ]))
    story += [strip, Spacer(1, 2),
              P(f"Headline figures for the {PORTFOLIO_NAME.lower()}.", "caption")]

    # ---------------- 1. Objective ----------------
    story += [
        P("1. Objective", "h1"),
        P("Measure how an equally weighted portfolio of five Indian large-cap stocks "
          "performed over the most recent two years, how much risk it carried, and "
          "where that risk came from. The analysis is descriptive: it explains what "
          "happened and why, and makes no forecast."),
        P("2. Business problem", "h1"),
        P("A portfolio analytics team has to answer three questions for every "
          "portfolio it reports on. Did it make money, and how did that compare with "
          "the market? Was the return worth the risk taken? Is the portfolio as "
          "diversified as its holdings suggest? Raw return alone cannot answer the "
          "last two, so this project combines return, volatility, drawdown, "
          "correlation and risk attribution into a single, repeatable workflow."),
    ]

    # ---------------- 3. Dataset ----------------
    w = res["weights"]
    rows = [["Company", "Yahoo ticker", "Sector", "Weight"]]
    tick = {v: t for t, v in config.STOCKS.items()}
    for name in w.index:
        rows.append([name, tick[name], config.SECTORS[name], pct(w[name], 0)])
    if res["has_benchmark"]:
        rows.append([f"{config.BENCHMARK_NAME} (benchmark)", config.BENCHMARK_TICKER,
                     "Broad market index", "n/a"])
    log = res["clean_log"]
    story += [
        P("3. Dataset and portfolio composition", "h1"),
        _table(rows, [1.9 * inch, 1.3 * inch, 2.2 * inch, 1.37 * inch], st,
               align_right_from=3),
        Spacer(1, 6),
        P(f"<b>Source.</b> Daily adjusted closing prices from Yahoo Finance, "
          f"downloaded with the open-source <i>yfinance</i> package"
          + (f" (version {download_info['yfinance_version']}) on "
             f"{download_info['downloaded_at'][:10]}" if download_info else "")
          + ". Adjusted prices include dividends and stock splits, so returns "
          "reflect what a shareholder actually earned."),
        P(f"<b>Cleaning.</b> {log['rows_raw']} raw dates were downloaded. "
          f"{log['duplicate_dates_removed']} duplicate dates and "
          f"{log['empty_dates_removed']} dates with no prices were removed, "
          f"{log['values_forward_filled']} isolated missing prices were filled with "
          f"the previous day's price (at most {config.MAX_FFILL_DAYS} days), and "
          f"{log['incomplete_dates_removed']} dates with remaining gaps were dropped. "
          f"The clean dataset has {log['rows_clean']} price dates "
          f"({log['rows_clean'] - 1} daily returns, since the first date has no "
          f"previous price) from "
          f"{fmt_date(log['first_date'])} to {fmt_date(log['last_date'])}, the same "
          f"dates for every security."),
    ]

    # ---------------- 4. Methodology ----------------
    rf_d = (1 + k["rf"]) ** (1 / config.TRADING_DAYS) - 1
    m_rows = [
        ["Metric", "Formula", "What it tells us"],
        ["Daily return", "r<sub>t</sub> = P<sub>t</sub> / P<sub>t-1</sub> - 1",
         "Percentage change in price from one trading day to the next"],
        ["Portfolio return", "r<sub>p</sub> = sum of w<sub>i</sub> x r<sub>i</sub>",
         "Weighted average of stock returns, with weights reset to 20% daily"],
        ["Cumulative return", "product of (1 + r<sub>t</sub>) - 1",
         "Total gain or loss over the whole period"],
        ["CAGR", "(1 + cumulative)<super>252/N</super> - 1",
         "Constant yearly return giving the same end value"],
        ["Volatility", "std(daily r) x sqrt(252)",
         "Typical size of swings around the average, per year"],
        ["Sharpe Ratio", "mean(r - r<sub>f</sub>) / std(r) x sqrt(252)",
         "Excess return earned per unit of risk"],
        ["Maximum drawdown", "min of (value / running peak - 1)",
         "Largest fall from a previous high"],
        ["Beta", "cov(r, r<sub>m</sub>) / var(r<sub>m</sub>)",
         "Sensitivity to moves in the NIFTY 50"],
        ["Risk contribution", "w<sub>i</sub> x (Cov w)<sub>i</sub> / sigma<sub>p</sub>",
         "Part of portfolio volatility caused by each stock"],
    ]
    story += [
        P("4. Methodology", "h1"),
        _table(m_rows, [1.35 * inch, 2.35 * inch, 3.07 * inch], st, align_right_from=9),
        Spacer(1, 6),
        P("<b>Assumptions.</b> " + " ".join([
            f"(1) {config.TRADING_DAYS} trading days per year, the market convention for "
            f"annualising (this dataset has about "
            f"{res['period']['observed_days_per_year']:.0f} NSE trading days a year).",
            f"(2) Risk-free rate of {pct(k['rf'], 2)} a year "
            f"({config.RISK_FREE_LABEL}), or {rf_d * 100:.4f}% a day.",
            "(3) Weights are held at 20% each day (daily rebalancing); buy-and-hold is "
            "shown for comparison.",
            "(4) No transaction costs or taxes.",
            "(5) Volatility uses the sample standard deviation.",
        ])),
    ]

    # ---------------- 5. Performance ----------------
    order = list(w.index) + [PORTFOLIO_NAME] + (
        [config.BENCHMARK_NAME] if res["has_benchmark"] else [])
    rows = [["Security", "Cumulative return", "CAGR", "Volatility", "Sharpe",
             "Max drawdown", "Beta"]]
    for name in order:
        r = s.loc[name]
        rows.append([name, pct(r["Cumulative return"]), pct(r["Annualised return (CAGR)"]),
                     pct(r["Annualised volatility"]), f"{r['Sharpe ratio']:.2f}",
                     pct(r["Max drawdown"]),
                     f"{r['Beta vs benchmark']:.2f}" if res["has_benchmark"] else "n/a"])
    bold = (order.index(PORTFOLIO_NAME) + 1,)
    story += [
        P("5. Performance analysis", "h1"),
        _image(chart_paths["growth"]),
        P("Figure 1. Value of Rs 100 invested on the first day of the period.", "caption"),
        _table(rows, [1.75 * inch] + [0.837 * inch] * 6, st, bold_rows=bold),
        P("Table 1. Performance and risk metrics, computed from daily adjusted prices.",
          "caption"),
    ]

    # ---------------- 6. Risk ----------------
    m = res["portfolio_mdd"]
    sens = res["sharpe_sensitivity"]
    s_rows = [["Security"] + [f"rf = {c}" for c in sens.columns]]
    for name in [PORTFOLIO_NAME] + ([config.BENCHMARK_NAME] if res["has_benchmark"] else []):
        s_rows.append([name] + [f"{v:.2f}" for v in sens.loc[name]])
    story += [
        KeepTogether([
            P("6. Risk analysis", "h1"),
            _image(chart_paths["drawdown"]),
            P(f"Figure 2. Drawdown of the portfolio. The deepest fall ran from "
              f"{fmt_date(m['peak_date'])} to {fmt_date(m['trough_date'])}.", "caption"),
        ]),
        KeepTogether([
            _image(chart_paths["risk_return"], width=CONTENT_W * 0.78),
            P("Figure 3. Each security's annualised return against its annualised "
              "volatility. Points higher and further left offer more return per unit "
              "of risk.", "caption"),
        ]),
        KeepTogether([
            P("Sharpe Ratio sensitivity to the risk-free rate", "h2"),
            P("The risk-free rate is an assumption, so the Sharpe Ratio is shown at "
              "several rates. Rankings that hold across the table do not depend on "
              "the exact rate chosen."),
            _table(s_rows, [2.3 * inch] + [1.117 * inch] * 4, st),
            Spacer(1, 4),
        ]),
    ]

    # ---------------- 7. Diversification ----------------
    d = res["diversification"]
    rc = res["risk_contribution"]
    d_rows = [
        ["Measure", "Value"],
        ["Weighted average stock volatility (no diversification)",
         pct(d["weighted_avg_vol"])],
        ["Actual portfolio volatility", pct(d["portfolio_vol"])],
        ["Volatility removed by diversification", pct(d["volatility_reduction"])],
        ["Diversification ratio", f"{d['diversification_ratio']:.2f}"],
        ["Average pairwise correlation", f"{d['avg_pairwise_corr']:.2f}"],
        ["Most correlated pair", f"{d['max_corr_pair'][0]} / {d['max_corr_pair'][1]} "
                                 f"({d['max_corr_pair'][2]:.2f})"],
        ["Least correlated pair", f"{d['min_corr_pair'][0]} / {d['min_corr_pair'][1]} "
                                  f"({d['min_corr_pair'][2]:.2f})"],
    ]
    r_rows = [["Stock", "Weight", "Share of risk", "Risk share minus weight",
               "Return contribution (pp a year)"]]
    for name, r in rc.iterrows():
        r_rows.append([name, pct(r["Weight"], 0), pct(r["Share of portfolio risk"]),
                       f"{r['Risk share minus weight'] * 100:+.1f} pp",
                       f"{r['Return contribution'] * 100:+.1f}"])
    story += [
        KeepTogether([
            P("7. Correlation and diversification", "h1"),
            _image(chart_paths["correlation"], width=CONTENT_W * 0.58),
            P("Figure 4. Correlation of daily returns. 1.00 means two stocks always move "
              "together; 0 means no linear relationship.", "caption"),
        ]),
        _table(d_rows, [4.2 * inch, 2.57 * inch], st),
        Spacer(1, 8),
        KeepTogether([
            _image(chart_paths["risk_contribution"], width=CONTENT_W * 0.78),
            P("Figure 5. Each stock's 20% capital weight next to its share of portfolio "
              "volatility (covariance-based risk contribution).", "caption"),
        ]),
        KeepTogether([
            _table(r_rows, [1.6 * inch, 0.9 * inch, 1.1 * inch, 1.5 * inch, 1.67 * inch], st),
            P("Table 2. Risk contribution adds up to 100% of portfolio volatility. Return "
          "contribution is weight x average annualised return, in percentage points; "
          "it adds up to the portfolio's average annual return (an arithmetic average, "
          "which is higher than CAGR when returns vary).", "caption"),
        ]),
    ]

    # ---------------- 8-11. Findings and conclusion ----------------
    findings = build_findings(res)
    story += [
        P("8. Key findings", "h1"),
        ListFlowable([ListItem(P(f"<b>{t}.</b> {x}"), leftIndent=12)
                      for t, x in findings], bulletType="1", leftIndent=14,
                     bulletFontSize=9),
        P("9. Business interpretation", "h1"),
        *[P(x) for x in business_interpretation(res)],
        P("10. Limitations", "h1"),
        ListFlowable([ListItem(P(x), leftIndent=12) for x in limitations()],
                     bulletType="bullet", leftIndent=14, bulletFontSize=7),
        P("11. Conclusion", "h1"),
        P(conclusion(res)),
        P("12. Tools and technologies", "h1"),
        P("Python 3; pandas for data handling and return calculations; NumPy for the "
          "covariance and risk attribution maths; Matplotlib for charts; yfinance for "
          "data download; ReportLab to generate this report. The full pipeline runs "
          "with one command and saves every intermediate table as CSV, so each number "
          "here can be checked."),
    ]

    # ---------------- Sources ----------------
    src = [f"Yahoo Finance, {name}: https://finance.yahoo.com/quote/{quote(t)}/"
           for t, name in config.STOCKS.items()]
    if res["has_benchmark"]:
        src.append(f"Yahoo Finance, {config.BENCHMARK_NAME}: "
                   f"https://finance.yahoo.com/quote/{quote(config.BENCHMARK_TICKER)}/")
    src.append(f"Risk-free rate ({config.RISK_FREE_LABEL}): "
               f"{config.RISK_FREE_SOURCE_URL}")
    story += [P("Sources", "h2")] + [P(x, "small") for x in src]

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=0.7 * inch, bottomMargin=0.85 * inch,
                            title=config.REPORT_TITLE, author=config.REPORT_AUTHOR)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path
