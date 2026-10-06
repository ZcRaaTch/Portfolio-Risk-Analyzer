"""
Unit tests on small, hand-calculable examples.
Run with:  python -m pytest -q
Each test states the answer you would get with a calculator.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics as a  # noqa: E402


def dates(n):
    return pd.bdate_range("2025-01-01", periods=n)


def test_daily_returns():
    p = pd.DataFrame({"X": [100.0, 110.0, 99.0]}, index=dates(3))
    r = a.daily_returns(p)["X"]
    assert r.tolist() == pytest.approx([0.10, -0.10])


def test_total_return_compounds():
    # +10% then -10% leaves you 1% down, not flat.
    r = pd.Series([0.10, -0.10])
    assert a.total_return(r) == pytest.approx(-0.01)


def test_cagr_of_one_year():
    # 252 equal daily returns that compound to +10% give a CAGR of exactly 10%.
    daily = 1.10 ** (1 / 252) - 1
    r = pd.Series([daily] * 252)
    assert a.annualised_return(r) == pytest.approx(0.10)


def test_volatility_scaling():
    r = pd.Series([0.01, -0.01, 0.02, -0.02])
    assert a.annualised_volatility(r) == pytest.approx(r.std() * np.sqrt(252))


def test_sharpe_zero_rf():
    r = pd.Series([0.01, -0.005, 0.02, 0.0])
    expected = r.mean() / r.std() * np.sqrt(252)
    assert a.sharpe_ratio(r, rf_annual=0.0) == pytest.approx(expected)


def test_daily_risk_free_compounds_back():
    rf_d = a.daily_risk_free(0.0526)
    assert (1 + rf_d) ** 252 - 1 == pytest.approx(0.0526)


def test_max_drawdown_dates():
    wealth = pd.Series([1.0, 1.2, 0.9, 1.0, 1.3], index=dates(5))
    m = a.max_drawdown(wealth)
    assert m["max_drawdown"] == pytest.approx(0.9 / 1.2 - 1)  # -25%
    assert m["peak_date"] == dates(5)[1].date().isoformat()
    assert m["trough_date"] == dates(5)[2].date().isoformat()
    assert m["recovery_date"] == dates(5)[4].date().isoformat()


def test_max_drawdown_not_recovered():
    wealth = pd.Series([1.0, 1.5, 1.2, 1.4], index=dates(4))
    assert a.max_drawdown(wealth)["recovery_date"] is None


def test_portfolio_return_is_weighted_average():
    r = pd.DataFrame({"A": [0.10, 0.0], "B": [0.0, 0.20]}, index=dates(2))
    p = a.portfolio_returns(r, {"A": 0.5, "B": 0.5})
    assert p.tolist() == pytest.approx([0.05, 0.10])


def test_buy_and_hold_drifts():
    prices = pd.DataFrame({"A": [100.0, 200.0], "B": [100.0, 100.0]}, index=dates(2))
    v = a.buy_and_hold_value(prices, {"A": 0.5, "B": 0.5})
    assert v.tolist() == pytest.approx([1.0, 1.5])


def test_wealth_index_starts_at_one():
    r = pd.Series([0.1, 0.1], index=dates(3)[1:])
    w = a.wealth_index(r, dates(3)[0])
    assert w.tolist() == pytest.approx([1.0, 1.1, 1.21])


def random_returns(seed=0, n=300):
    rng = np.random.default_rng(seed)
    cols = ["A", "B", "C"]
    data = rng.normal(0.0005, 0.015, size=(n, 3))
    data[:, 1] += 0.6 * data[:, 0]  # make B correlated with A
    return pd.DataFrame(data, columns=cols, index=dates(n))


def test_risk_contributions_add_up():
    r = random_returns()
    w = {"A": 0.5, "B": 0.3, "C": 0.2}
    rc = a.risk_contribution(r, w)
    port_vol = a.annualised_volatility(a.portfolio_returns(r, w))
    assert rc["Volatility contribution"].sum() == pytest.approx(port_vol)
    assert rc["Share of portfolio risk"].sum() == pytest.approx(1.0)


def test_return_contributions_add_up():
    r = random_returns()
    w = {"A": 0.5, "B": 0.3, "C": 0.2}
    rc = a.risk_contribution(r, w)
    port_mean = a.annualised_mean_return(a.portfolio_returns(r, w))
    assert rc["Return contribution"].sum() == pytest.approx(port_mean)


def test_diversification_matches_direct_volatility():
    r = random_returns()
    w = {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
    d = a.diversification_stats(r, w)
    direct = a.annualised_volatility(a.portfolio_returns(r, w))
    assert d["portfolio_vol"] == pytest.approx(direct)
    assert d["diversification_ratio"] >= 1.0  # can never be below 1
    assert d["max_corr_pair"][:2] == ["A", "B"]


def test_beta_of_market_is_one():
    r = random_returns()["A"]
    assert a.beta(r, r) == pytest.approx(1.0)
    assert a.beta(2 * r, r) == pytest.approx(2.0)


def test_cleaning_steps():
    idx = pd.to_datetime(["2025-01-02", "2025-01-01", "2025-01-03", "2025-01-03",
                          "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09",
                          "2025-01-10"])
    raw = pd.DataFrame({
        "A": [101, 100, np.nan, 102, np.nan, 104, np.nan, np.nan, np.nan],
        "B": [201, 200, np.nan, 202, np.nan, 204, 205, 206, 207],
    }, index=idx, dtype=float)
    clean, log = a.clean_prices(raw, max_ffill=2)
    assert log["duplicate_dates_removed"] == 1          # 3 Jan appears twice
    assert clean.index.is_monotonic_increasing
    assert clean.loc["2025-01-07", "A"] == 104
    # A's gap of 3 days after 7 Jan: 8 and 9 Jan filled, 10 Jan dropped.
    assert "2025-01-09" in clean.index.strftime("%Y-%m-%d")
    assert "2025-01-10" not in clean.index.strftime("%Y-%m-%d")
    assert not clean.isna().any().any()


def test_cleaning_rejects_bad_prices():
    raw = pd.DataFrame({"A": [100.0, 0.0]}, index=dates(2))
    with pytest.raises(ValueError):
        a.clean_prices(raw)
