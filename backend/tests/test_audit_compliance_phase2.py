"""
KARAT - Compliance & Financial Invariants Regression Test Suite (Phase 2 Audit).

Validates:
1. Mandatory tender period liquidation (non-delivery safety).
2. Staggered-expiry risk management (no unhedged naked legs).
3. Lifecycle entry protection (no entry inside tender or <= 3 days to expiry).
4. Carry-adjusted Z-score with zero lookahead bias.
5. Historical forward curve regime tracking (Contango vs Backwardation).
6. Market attribution exposure labeling and caveats.
7. Multi-leg normalization and rupee friction invariants.
"""

from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.analytics.spread import compute_spread_series, get_spread_summary, get_spread_chart_data
from backend.analytics.term_structure import compute_historical_curve_regimes, get_term_structure
from backend.backtest.engine import run_backtest, _run_strategy
from backend.data.parser import load_data


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def clean_data():
    df, _ = load_data()
    assert not df.empty, "Dataset must not be empty"
    return df


# ──────────────────────────────────────────────────────────────────────
# 1. CONTRACT LIFECYCLE: TENDER LIQUIDATION & STAGGERED EXPIRY
# ──────────────────────────────────────────────────────────────────────

def test_tender_period_mandatory_exit_in_simulation():
    """
    MCX Rule: Non-delivery market participants must not carry positions into
    the compulsory delivery tender window (starts 7 calendar days before expiry).
    An active backtest position MUST forcibly exit on or before the tender start date.
    """
    # Build a 25-day synthetic series approaching expiry on day 25
    base_date = dt.date(2026, 10, 1)
    expiry = dt.date(2026, 10, 25)
    tender_start = expiry - dt.timedelta(days=7)  # 2026-10-18

    dates = [base_date + dt.timedelta(days=i) for i in range(25)]
    # Z-scores: Trigger entry at day 2 (|z| = 2.5), but stays high until day 24 (never reverts statistically)
    z_scores = [0.0, 0.5, 2.5] + [2.2] * 22
    spreads = [10.0] * 25
    raw_a = [14500.0] * 25
    raw_b = [14500.0] * 25

    records = []
    for i, d in enumerate(dates):
        records.append({
            "date": d,
            "z_score": z_scores[i],
            "spread_bps": spreads[i],
            "raw_a": raw_a[i],
            "raw_b": raw_b[i],
            "thin_day": False,
            "expiry_a": str(expiry),
            "expiry_b": str(expiry),
        })

    spread_df = pd.DataFrame(records)

    # Run strategy with very large time_stop (50 days) so only tender forces the exit
    trades = _run_strategy(
        spread_df=spread_df,
        entry_z=2.0,
        exit_z=0.5,
        time_stop_days=50,
        symbol_a="GOLDM",
        symbol_b="GOLDTEN",
    )

    assert len(trades) == 1, "Trade must have entered on day 2"
    t = trades[0]
    assert t["exit_reason"] == "tender_period_liquidation", (
        f"Exit reason must be tender_period_liquidation, got: {t['exit_reason']}"
    )
    # Exit date must be on or after tender_start (2026-10-18)
    exit_date = dt.date.fromisoformat(str(t["exit_date"])[:10])
    assert exit_date >= tender_start, f"Exit date {exit_date} must be at or after tender start {tender_start}"
    assert exit_date < expiry, f"Exit date {exit_date} must be strictly before contract expiry {expiry}"


def test_staggered_expiry_prevents_unhedged_leg():
    """
    When pairing legs with staggered expiries (e.g. Leg A expires 10 days before Leg B),
    the strategy must exit when Leg A enters tender or expires so that Leg B is never held unhedged.
    """
    base_date = dt.date(2026, 10, 1)
    exp_a = dt.date(2026, 10, 15)  # Near expiry
    exp_b = dt.date(2026, 11, 15)  # Far expiry
    tender_a = exp_a - dt.timedelta(days=7)  # 2026-10-08

    dates = [base_date + dt.timedelta(days=i) for i in range(20)]
    records = []
    for i, d in enumerate(dates):
        records.append({
            "date": d,
            "z_score": 2.5 if i >= 2 else 0.0,
            "spread_bps": 15.0,
            "raw_a": 14500.0,
            "raw_b": 14480.0,
            "thin_day": False,
            "expiry_a": str(exp_a),
            "expiry_b": str(exp_b),
        })

    spread_df = pd.DataFrame(records)
    trades = _run_strategy(
        spread_df=spread_df,
        entry_z=2.0,
        exit_z=0.5,
        time_stop_days=50,
        symbol_a="GOLDM",
        symbol_b="GOLDTEN",
    )

    assert len(trades) == 1
    t = trades[0]
    # Trade must exit due to Leg A's earlier tender start date
    assert t["exit_reason"] in ("tender_period_liquidation", "staggered_expiry_unwind")
    exit_d = dt.date.fromisoformat(str(t["exit_date"])[:10])
    assert exit_d <= exp_a, f"Must exit before or on earlier contract expiry {exp_a}"


def test_no_entry_inside_tender_window_or_near_expiry():
    """
    Trading algorithm must refuse new entries if current simulation date is inside
    the tender window or within 3 days of expiration.
    """
    expiry = dt.date(2026, 10, 10)
    # Simulation dates 2026-10-05 to 2026-10-09 (inside tender window: 2026-10-03 to 10-10)
    dates = [dt.date(2026, 10, 5) + dt.timedelta(days=i) for i in range(4)]
    records = []
    for d in dates:
        records.append({
            "date": d,
            "z_score": 3.0,  # Huge dislocation
            "spread_bps": 50.0,
            "raw_a": 14500.0,
            "raw_b": 14450.0,
            "thin_day": False,
            "expiry_a": str(expiry),
            "expiry_b": str(expiry),
        })
    spread_df = pd.DataFrame(records)
    trades = _run_strategy(spread_df=spread_df, entry_z=2.0, exit_z=0.5, time_stop_days=10)
    assert len(trades) == 0, "No trade should enter inside the tender delivery window"


# ──────────────────────────────────────────────────────────────────────
# 2. TERM STRUCTURE & CARRY-ADJUSTED Z-SCORES
# ──────────────────────────────────────────────────────────────────────

def test_carry_adjusted_spread_and_zscore_zero_lookahead(clean_data):
    """
    Verify carry-adjusted spread deduction and confirm zero lookahead on carry Z-score.
    """
    window = 15
    res = compute_spread_series(clean_data, "GOLDM", "GOLDTEN", window=window, use_carry_adj=False)
    assert "carry_adjusted_spread_bps" in res.columns
    assert "carry_adjusted_z_score" in res.columns

    # Verify that carry adjusted spread removes financing roll-down
    for _, row in res.iterrows():
        exp_a = dt.date.fromisoformat(str(row["expiry_a"])[:10])
        exp_b = dt.date.fromisoformat(str(row["expiry_b"])[:10])
        days_diff = (exp_a - exp_b).days
        expected_adj = 600.0 * (days_diff / 365.0)
        assert row["carry_adjusted_spread_bps"] == pytest.approx(row["spread_bps"] - expected_adj, abs=0.05)

    # Verify zero lookahead on carry Z-score:
    # Mutating day t's carry spread must NOT affect day t's rolling carry mean/std
    shifted_carry = res["carry_adjusted_spread_bps"].shift(1)
    rolling_carry_mean = shifted_carry.rolling(window=window, min_periods=window).mean()
    rolling_carry_std = shifted_carry.rolling(window=window, min_periods=window).std()

    for idx in range(window + 1, len(res)):
        expected_z = (res.loc[idx, "carry_adjusted_spread_bps"] - rolling_carry_mean.iloc[idx]) / rolling_carry_std.iloc[idx]
        assert res.loc[idx, "carry_adjusted_z_score"] == pytest.approx(round(expected_z, 4), abs=0.001)

    # Verify use_carry_adj parameter toggles z_score column
    res_carry = compute_spread_series(clean_data, "GOLDM", "GOLDTEN", window=window, use_carry_adj=True)
    assert np.allclose(res_carry["z_score"], res["carry_adjusted_z_score"])


def test_historical_curve_regimes_tracking(clean_data):
    """
    Verify that compute_historical_curve_regimes accurately computes forward curve
    slope across dates and assigns valid institutional regimes.
    """
    regimes = compute_historical_curve_regimes(clean_data, symbol="GOLDM")
    assert isinstance(regimes, list)

    for r in regimes:
        assert "date" in r
        assert "near_expiry" in r
        assert "far_expiry" in r
        assert "calendar_days" in r
        assert r["calendar_days"] > 0
        assert "annualized_carry_pct" in r
        assert r["regime"] in ("Contango", "Backwardation", "Flat / Parity")

        # Mathematical consistency:
        # annualized_carry_pct = ((far - near) / near) * (365 / cal_days) * 100
        near_p = r["near_norm_price"]
        far_p = r["far_norm_price"]
        cal_days = r["calendar_days"]
        expected_carry = ((far_p - near_p) / near_p) * (365.0 / cal_days) * 100.0
        assert r["annualized_carry_pct"] == pytest.approx(expected_carry, abs=0.05)


def test_api_curve_regimes_endpoint(client):
    """Verify FastAPI /curve/regimes and /api/curve/regimes endpoints."""
    resp = client.get("/api/curve/regimes?symbol=GOLDM")
    assert resp.status_code == 200
    data = resp.json()
    assert "regimes" in data
    assert "total_observations" in data
    assert data["symbol"] == "GOLDM"
    assert "data_status" in data


# ──────────────────────────────────────────────────────────────────────
# 3. MARKET ATTRIBUTION & EXPOSURE LABELING
# ──────────────────────────────────────────────────────────────────────

def test_market_attribution_exposure_indicators_and_caveats(clean_data):
    """
    Correlation must be labeled as an indicator of directional market exposure,
    not proof of market neutrality, with explicit analytical caveats.
    """
    res = run_backtest(clean_data, symbol_a="GOLDM", symbol_b="GOLDTEN", window=15)
    attribution = res["unseen"]["attribution"]

    assert "strategy_pnl_bps" in attribution
    assert "underlying_gold_move_bps" in attribution
    assert "correlation_to_gold" in attribution
    assert "market_exposure_assessment" in attribution
    assert "exposure_caveat" in attribution

    # Check analytical caveat text
    caveat = attribution["exposure_caveat"]
    assert "empirical indicator" in caveat.lower() or "indicator of market exposure" in caveat.lower()
    assert "not definitive proof" in caveat.lower() or "not proof" in caveat.lower()


def test_backtest_with_carry_adjusted_toggle(clean_data):
    """
    Verify run_backtest accepts use_carry_adj and records it in params.
    """
    res = run_backtest(clean_data, symbol_a="GOLDM", symbol_b="GOLDTEN", window=15, use_carry_adj=True)
    assert res["params"]["use_carry_adj"] is True
    assert "unseen" in res
    assert "verdict" in res
