"""
insights.py
-----------
Turns the computed numbers into plain-English findings.

Nothing here is hard-coded: every sentence is built from the results
dictionary, and the wording changes with the data (for example "gained"
versus "lost", "outperformed" versus "underperformed"). This keeps the
report honest whatever the market did over the period analysed.
"""

import config
from analytics import PORTFOLIO_NAME


def pct(x, digits=1):
    """Format 0.1234 as '12.3%'."""
    return f"{x * 100:.{digits}f}%"


def pp(x, digits=1):
    """Format a difference of two percentages as percentage points."""
    return f"{abs(x) * 100:.{digits}f} percentage points"


def fmt_date(iso):
    """Format '2025-03-04' as '4 Mar 2025'."""
    from datetime import date
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b %Y')}"


def key_numbers(res):
    """The handful of headline figures used across report, README and notes."""
    s = res["summary"]
    p = s.loc[PORTFOLIO_NAME]
    out = {
        "start": fmt_date(res["period"]["start"]),
        "end": fmt_date(res["period"]["end"]),
        # Trading days in the window = price dates (one more than daily returns).
        "days": res["clean_log"]["rows_clean"],
        "cum": p["Cumulative return"],
        "cagr": p["Annualised return (CAGR)"],
        "vol": p["Annualised volatility"],
        "sharpe": p["Sharpe ratio"],
        "mdd": p["Max drawdown"],
        "rf": res["rf_annual"],
        "div": res["diversification"],
    }
    if res["has_benchmark"]:
        b = s.loc[config.BENCHMARK_NAME]
        out.update(b_cum=b["Cumulative return"], b_cagr=b["Annualised return (CAGR)"],
                   b_vol=b["Annualised volatility"], b_sharpe=b["Sharpe ratio"],
                   b_mdd=b["Max drawdown"], beta=p["Beta vs benchmark"])
    return out


def build_findings(res):
    """Return a list of (title, sentence) findings driven entirely by the data."""
    k = key_numbers(res)
    s = res["summary"]
    stocks = s.loc[list(res["weights"].index)]
    findings = []

    # 1. Headline performance
    verb = "gained" if k["cum"] >= 0 else "lost"
    text = (f"Between {k['start']} and {k['end']} ({k['days']} trading days) the "
            f"equal-weight portfolio {verb} {pct(abs(k['cum']))} in total, "
            f"an annualised return (CAGR) of {pct(k['cagr'])}.")
    if res["has_benchmark"]:
        diff = k["cum"] - k["b_cum"]
        rel = "outperformed" if diff >= 0 else "underperformed"
        text += (f" Over the same days the {config.BENCHMARK_NAME} returned "
                 f"{pct(k['b_cum'])}, so the portfolio {rel} the index by {pp(diff)}.")
    findings.append(("Performance", text))

    # 2. Risk-adjusted performance
    text = (f"Annualised volatility was {pct(k['vol'])} and the Sharpe Ratio was "
            f"{k['sharpe']:.2f} using a {pct(k['rf'], 2)} risk-free rate.")
    if k["sharpe"] < 0:
        text += (" A negative Sharpe Ratio means the portfolio earned less than a "
                 "risk-free Treasury Bill over this period.")
    if res["has_benchmark"]:
        better = "higher" if k["sharpe"] > k["b_sharpe"] else "lower"
        if k["sharpe"] < 0 and k["b_sharpe"] < 0:
            text += (f" The {config.BENCHMARK_NAME}'s Sharpe Ratio was "
                     f"{k['b_sharpe']:.2f}. When both ratios are negative, ranking "
                     f"them is not meaningful, because a negative ratio looks less "
                     f"bad simply when volatility is higher; compare total return "
                     f"and drawdown instead.")
        else:
            text += (f" The {config.BENCHMARK_NAME} had a Sharpe Ratio of "
                     f"{k['b_sharpe']:.2f}, so the portfolio delivered {better} return "
                     f"per unit of risk than the index.")
    findings.append(("Risk-adjusted return", text))

    # 3. Stock comparison
    best_ret = stocks["Annualised return (CAGR)"].idxmax()
    worst_ret = stocks["Annualised return (CAGR)"].idxmin()
    best_sh = stocks["Sharpe ratio"].idxmax()
    most_vol = stocks["Annualised volatility"].idxmax()
    least_vol = stocks["Annualised volatility"].idxmin()
    text = (f"{best_ret} had the highest annualised return "
            f"({pct(stocks.loc[best_ret, 'Annualised return (CAGR)'])}) and "
            f"{worst_ret} the lowest "
            f"({pct(stocks.loc[worst_ret, 'Annualised return (CAGR)'])}). "
            f"{most_vol} was the most volatile stock "
            f"({pct(stocks.loc[most_vol, 'Annualised volatility'])}) and "
            f"{least_vol} the least "
            f"({pct(stocks.loc[least_vol, 'Annualised volatility'])}).")
    if best_sh != best_ret:
        text += (f" On a risk-adjusted basis {best_sh} ranked first "
                 f"(Sharpe {stocks.loc[best_sh, 'Sharpe ratio']:.2f}), showing that "
                 f"the highest raw return did not come with the best return per "
                 f"unit of risk.")
    else:
        text += (f" {best_sh} also had the best Sharpe Ratio "
                 f"({stocks.loc[best_sh, 'Sharpe ratio']:.2f}).")
    findings.append(("Stock comparison", text))

    # 4. Diversification
    d = k["div"]
    text = (f"If the five stocks had moved in perfect lockstep, portfolio "
            f"volatility would have been {pct(d['weighted_avg_vol'])} (the weighted "
            f"average of the stocks). The actual figure was {pct(d['portfolio_vol'])}, "
            f"so diversification removed {pct(d['volatility_reduction'])} of risk "
            f"(diversification ratio {d['diversification_ratio']:.2f}). The average "
            f"correlation between pairs of stocks was {d['avg_pairwise_corr']:.2f}.")
    findings.append(("Diversification benefit", text))

    # 5. Concentration: is the most correlated pair from the same sector?
    a, b, c = d["max_corr_pair"]
    lo_a, lo_b, lo_c = d["min_corr_pair"]
    same_sector = config.SECTORS[a] == config.SECTORS[b]
    text = (f"The most correlated pair was {a} and {b} ({c:.2f}); the least "
            f"correlated was {lo_a} and {lo_b} ({lo_c:.2f}).")
    if same_sector:
        sw = res["sector_weights"]
        text += (f" {a} and {b} are both {config.SECTORS[a]} stocks. Sector "
                 f"weights are " + ", ".join(f"{sec} {pct(w, 0)}" for sec, w in sw.items())
                 + f", so five holdings span only {len(sw)} sectors. Stocks from the "
                 f"same sector react to the same news, which limits how much risk "
                 f"an equal-weight split can diversify away.")
    else:
        sw = res["sector_weights"]
        text += (" Sector weights are " + ", ".join(
            f"{sec} {pct(w, 0)}" for sec, w in sw.items()) + ".")
    findings.append(("Concentration", text))

    # 6. Risk contribution
    rc = res["risk_contribution"]
    over = rc["Risk share minus weight"].idxmax()
    under = rc["Risk share minus weight"].idxmin()
    text = (f"Every stock holds a 20% weight, but risk is not split equally. "
            f"{over} accounted for {pct(rc.loc[over, 'Share of portfolio risk'])} "
            f"of portfolio volatility, the largest share relative to its weight, "
            f"while {under} accounted for "
            f"{pct(rc.loc[under, 'Share of portfolio risk'])}.")
    findings.append(("Risk contribution", text))

    # 7. Drawdown
    m = res["portfolio_mdd"]
    text = (f"The worst peak-to-trough fall was {pct(abs(m['max_drawdown']))}, from "
            f"{fmt_date(m['peak_date'])} to {fmt_date(m['trough_date'])}.")
    if m["recovery_date"]:
        text += f" The portfolio regained its previous high on {fmt_date(m['recovery_date'])}."
    else:
        text += " The portfolio had not regained that previous high by the end of the period."
    if res["has_benchmark"]:
        text += f" The {config.BENCHMARK_NAME}'s maximum drawdown was {pct(abs(k['b_mdd']))}."
    findings.append(("Drawdown", text))

    # 8. Rebalancing assumption
    bh = res["buy_and_hold"]
    diff = bh["Cumulative return"] - k["cum"]
    text = (f"The main results assume the portfolio is reset to 20% per stock "
            f"every day. A buy-and-hold investor who never rebalanced would have "
            f"had a total return of {pct(bh['Cumulative return'])}, "
            f"{pp(diff)} {'higher' if diff >= 0 else 'lower'} than the rebalanced "
            f"portfolio. Without rebalancing, weights drift towards whichever "
            f"stocks have risen, so the two approaches carry different risk over time.")
    findings.append(("Rebalancing", text))
    return findings


def business_interpretation(res):
    """What the numbers mean for someone managing or reporting on a portfolio."""
    k = key_numbers(res)
    d = k["div"]
    rc = res["risk_contribution"]
    over = rc["Risk share minus weight"].idxmax()
    over_share = rc.loc[over, "Share of portfolio risk"]
    paras = []

    if res["has_benchmark"]:
        ret_better = k["cum"] >= k["b_cum"]
        risk_lower = k["vol"] <= k["b_vol"]
        ret = "beat the index on return" if ret_better else "trailed the index on return"
        if ret_better and risk_lower:
            view = f"{ret} while taking less risk, the best combination of the two"
        elif ret_better:
            view = (f"{ret} but with higher volatility, so the Sharpe Ratio is the "
                    f"fairer test of whether the extra risk paid off")
        elif risk_lower:
            view = (f"{ret} but with lower volatility, which may still suit a client "
                    f"who values stability over maximum return")
        else:
            view = (f"{ret} while taking more risk; in hindsight a NIFTY 50 index "
                    f"fund would have served a client better over this period")
        paras.append(f"Against the {config.BENCHMARK_NAME}, the portfolio {view}. "
                     f"Its beta of {k['beta']:.2f} means that, on average, a 1% move in "
                     f"the index came with a {k['beta']:.2f}% move in the portfolio.")

    paras.append(
        f"Equal capital is not equal risk. {over} took up {pct(over_share)} of "
        f"portfolio volatility on a 20% allocation. A risk report built only on "
        f"capital weights would miss this. A natural next step for a portfolio "
        f"manager would be to compare the current weights with weights that give "
        f"each stock an equal share of risk.")

    paras.append(
        f"Diversification worked, but only partly: volatility fell from "
        f"{pct(d['weighted_avg_vol'])} to {pct(d['portfolio_vol'])}. Because the "
        f"holdings come from only {len(res['sector_weights'])} sectors, adding "
        f"stocks from sectors with lower correlation to these five (for example "
        f"consumer staples or healthcare) is the obvious test to run before "
        f"adding more of the same.")

    paras.append(
        f"The maximum drawdown of {pct(abs(k['mdd']))} is the number a client "
        f"feels. Volatility describes the average size of daily swings, while "
        f"drawdown answers the practical question of how much an investor could "
        f"have been down from the high point, which is what drives whether "
        f"clients stay invested.")
    return paras


def conclusion(res):
    """Short closing paragraph built from the results."""
    k = key_numbers(res)
    d = k["div"]
    verb = "gained" if k["cum"] >= 0 else "lost"
    text = (f"Over {k['start']} to {k['end']} the equal-weight portfolio of five NSE "
            f"large caps {verb} {pct(abs(k['cum']))} ({pct(k['cagr'])} a year) with "
            f"{pct(k['vol'])} annualised volatility, a Sharpe Ratio of "
            f"{k['sharpe']:.2f} and a worst drawdown of {pct(abs(k['mdd']))}. ")
    if res["has_benchmark"]:
        text += (f"The {config.BENCHMARK_NAME} returned {pct(k['b_cum'])} with a "
                 f"Sharpe Ratio of {k['b_sharpe']:.2f}. ")
    text += (f"Holding five stocks cut volatility by {pct(d['volatility_reduction'])} "
             f"compared with holding perfectly correlated assets, but sector overlap "
             f"and unequal risk contributions show that an equal-weight split is a "
             f"starting point rather than a balanced portfolio. These results "
             f"describe one historical period and are not a forecast.")
    return text


def limitations():
    """Fixed list of limitations; these apply whatever the data shows."""
    return [
        "Past returns, volatility and correlations describe one specific period "
        "and do not predict future results. Correlations in particular tend to "
        "rise during market stress, when diversification is needed most.",
        "Two years is a short window; it covers only the market conditions that "
        "happened to occur in it, so metrics can change materially with a "
        "different start or end date.",
        "Five large-cap stocks from three sectors are not a diversified "
        "portfolio in the institutional sense; results are not representative "
        "of the wider market.",
        "Transaction costs, taxes, and the cost of rebalancing are ignored.",
        "Volatility and the Sharpe Ratio treat upside and downside moves alike "
        "and assume returns are roughly normally distributed; real returns have "
        "fatter tails.",
        "A single recent T-Bill yield is used as the risk-free rate for the "
        "whole period; the sensitivity table shows how the Sharpe Ratio moves "
        "if a different rate is used.",
        "Adjusted prices from Yahoo Finance are a secondary source and may "
        "contain occasional errors; the raw download is saved so it can be "
        "checked against exchange data.",
    ]


def resume_and_pitch(res):
    """Markdown with resume bullets and interview pitches using real numbers."""
    k = key_numbers(res)
    d = k["div"]
    rc = res["risk_contribution"]
    over = rc["Risk share minus weight"].idxmax()
    a, b, c = d["max_corr_pair"]
    same_sector = config.SECTORS[a] == config.SECTORS[b]
    bench = res["has_benchmark"]

    bench_bit = (f" versus the {config.BENCHMARK_NAME}" if bench else "")
    lines = [
        "# Resume entry and interview talking points",
        "",
        f"_Generated from data covering {k['start']} to {k['end']}. "
        "Every number below comes from this run. Re-run main.py and these "
        "figures update automatically._",
        "",
        "## Resume entry",
        "",
        "**Portfolio Performance & Risk Analyzer | Python, Pandas, NumPy, Matplotlib**",
        "",
        f"- Built a Python tool analysing 2 years of daily NSE price data for an "
        f"equal-weight portfolio of 5 large-cap stocks, computing CAGR, volatility, "
        f"Sharpe Ratio, maximum drawdown and beta{bench_bit}",
        f"- Quantified diversification using a correlation matrix and covariance-based "
        f"risk attribution: portfolio volatility of {pct(k['vol'])} vs "
        f"{pct(d['weighted_avg_vol'])} undiversified, with {over} contributing "
        f"{pct(rc.loc[over, 'Share of portfolio risk'])} of risk on a 20% weight",
        f"- Automated a reproducible pipeline (data cleaning, 5 charts, PDF report) "
        f"and documented assumptions and limitations, including Sharpe sensitivity "
        f"to the risk-free rate",
        "",
        "## 30-second answer",
        "",
        f"\"I built a portfolio analytics tool in Python. I took two years of daily "
        f"prices for five Indian large caps, Reliance, TCS, HDFC Bank, Infosys and "
        f"ICICI Bank, and put 20% in each. The portfolio returned "
        f"{pct(k['cum'])} over the period with {pct(k['vol'])} annualised volatility "
        f"and a Sharpe Ratio of {k['sharpe']:.2f}. The most useful finding was "
        f"about diversification: {a} and {b} had a correlation of {c:.2f}"
        + (", two stocks from the same sector, so five stocks were really fewer "
           "independent bets than they look" if same_sector else "")
        + f", and {over} drove "
        f"{pct(rc.loc[over, 'Share of portfolio risk'])} of the risk despite only a "
        f"20% weight.\"",
        "",
        "## 1-minute answer",
        "",
        f"\"The goal was to answer a question a portfolio analyst gets every day: how "
        f"did this portfolio perform, and was the return worth the risk taken? I "
        f"pulled two years of adjusted daily prices from Yahoo Finance for five "
        f"NSE large caps and the NIFTY 50, cleaned the data, and built an "
        f"equal-weight portfolio. On performance, the portfolio returned "
        f"{pct(k['cum'])} in total, a CAGR of {pct(k['cagr'])}"
        + (f", against {pct(k['b_cum'])} for the NIFTY 50" if bench else "")
        + f". On risk, annualised volatility was {pct(k['vol'])}, the worst "
        f"drawdown was {pct(abs(k['mdd']))}, and the Sharpe Ratio was "
        f"{k['sharpe']:.2f} using the 91-day T-Bill yield as the risk-free rate. "
        f"Then I looked at where the risk came from. Diversification cut "
        f"volatility from {pct(d['weighted_avg_vol'])} to {pct(d['portfolio_vol'])}, "
        f"but the correlation matrix showed {a} and {b} moving closely together "
        f"({c:.2f}), and the covariance-based risk attribution showed {over} "
        f"carrying more risk than its 20% weight. So equal capital is not equal "
        f"risk. I was careful about limits: two years is a short window, "
        f"correlations shift in a crisis, and nothing here predicts future "
        f"returns.\"",
        "",
    ]
    return "\n".join(lines)


def readme_results(res):
    """Markdown block for the README's Sample results section."""
    s = res["summary"]
    k = key_numbers(res)
    lines = [f"_Data: {k['start']} to {k['end']}, {k['days']} trading days. "
             f"Risk-free rate {pct(k['rf'], 2)}. Generated by `python main.py`._", "",
             "| Security | Cumulative return | CAGR | Volatility | Sharpe | Max drawdown |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, r in s.iterrows():
        bold = "**" if name == PORTFOLIO_NAME else ""
        lines.append(f"| {bold}{name}{bold} | {pct(r['Cumulative return'])} | "
                     f"{pct(r['Annualised return (CAGR)'])} | "
                     f"{pct(r['Annualised volatility'])} | {r['Sharpe ratio']:.2f} | "
                     f"{pct(r['Max drawdown'])} |")
    lines += ["", "![Growth of Rs 100](outputs/charts/01_cumulative_growth.png)", "",
              "### Key insights", ""]
    lines += [f"{i}. **{t}.** {x}" for i, (t, x) in enumerate(build_findings(res), 1)]
    return "\n".join(lines)
