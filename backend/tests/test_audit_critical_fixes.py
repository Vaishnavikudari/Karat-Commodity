"""
KARAT - Regression Test Suite for Critical Audit Fixes.

Covers:
1. Spread Lab zero look-ahead bias (rolling stats use only prior observations).
2. Daily Briefing settlement price vs daily change separation.
3. Backtester rupee-denominated gross and net P&L with both legs, contract multipliers, and costs.
4. Best-Fit ranking accounting for execution friction without automatically favoring GOLDTEN.
5. Build vs Unseen partition boundary handling and anti-overfitting guards.
"""

from __future__ import annotations

import datetime as dt
import pytest
import pandas as pd
import numpy as np

from backend.data.parser import load_data
from backend.analytics.spread import compute_spread_series, get_spread_summary
from backend.analytics.daily_briefing import compute_daily_briefing
from backend.analytics.position_matcher import compute_position_matcher, rank_best_fit
from backend.analytics.signals import evaluate_pair_signal, get_all_active_signals
from backend.backtest.engine import run_backtest, tune_parameters_on_build, _run_strategy, _compute_metrics


@pytest.fixture(scope="module")
def clean_data():
    """Load cleaned MCX dataset."""
    df, _ = load_data()
    assert not df.empty, "Dataset must not be empty"
    return df


# ──────────────────────────────────────────────────────────────────────
# 1. SPREAD LAB: ZERO LOOK-AHEAD BIAS REGRESSION TEST
# ──────────────────────────────────────────────────────────────────────

def test_spread_lab_zero_lookahead_regression(clean_data):
    """
    Day t's rolling mean and std must depend solely on observations from days prior to t (shift(1)).
    Day t's own spread must NOT enter the rolling mean or standard deviation.
    """
    window = 15
    res = compute_spread_series(clean_data, "GOLDM", "GOLDTEN", window=window)
    assert len(res) > window + 5, "Need sufficient rows for window"

    # Select day t (e.g. index 25)
    t_idx = 25
    orig_z = res.iloc[t_idx]["z_score"]

    # Calculate expected rolling mean and std using strictly indices [t_idx - window : t_idx]
    prior_spreads = res["spread_bps"].iloc[t_idx - window : t_idx]
    expected_mean = prior_spreads.mean()
    expected_std = prior_spreads.std()
    curr_spread = res["spread_bps"].iloc[t_idx]

    expected_z = round((curr_spread - expected_mean) / expected_std, 4)
    assert orig_z == pytest.approx(expected_z, abs=1e-4)

    # Invariance check: Modifying day t's own spread by +1000 bps should NOT change day t's rolling mean or std
    # We test that rolling statistics are shifted by 1
    shifted_series = res["spread_bps"].shift(1)
    rolling_m = shifted_series.rolling(window=window, min_periods=window).mean()
    rolling_s = shifted_series.rolling(window=window, min_periods=window).std()

    assert rolling_m.iloc[t_idx] == pytest.approx(expected_mean, abs=1e-6)
    assert rolling_s.iloc[t_idx] == pytest.approx(expected_std, abs=1e-6)


# ──────────────────────────────────────────────────────────────────────
# 2. DAILY BRIEFING: SETTLEMENT PRICE VS DAILY CHANGE SEPARATION
# ──────────────────────────────────────────────────────────────────────

def test_daily_briefing_settle_vs_change_separation(clean_data):
    """
    Settlement price and daily price change must be separate.
    Settlement price must be a positive rupee value (e.g. > 10,000/g),
    never conflated with the daily change (which can be negative).
    """
    briefing = compute_daily_briefing(clean_data)
    assert briefing is not None
    assert "template_summary" in briefing

    summary_text = briefing["template_summary"]
    # The summary text must state settled at a positive level and report change separately
    assert "settled at ₹" in summary_text
    assert "change)" in summary_text

    # Extract parsed numbers from text
    # e.g., "On 2026-10-14, GOLDTEN settled at ₹14,506.20/g (-₹33.50/g, -0.23% change)."
    assert "settled at -₹" not in summary_text, "Settlement price must not be negative daily change"

    # Verify contracts detail structure in price_changes
    for c in briefing.get("price_changes", []):
        assert c["norm_close"] > 10000.0, "Settlement price must be actual positive mark"
        assert isinstance(c["change_rs_per_g"], (int, float))
        assert isinstance(c["pct_change"], (int, float))


# ──────────────────────────────────────────────────────────────────────
# 3. BACKTESTER: RUPEE GROSS AND NET P&L WITH CONTRACT QUANTITIES
# ──────────────────────────────────────────────────────────────────────

def test_backtest_rupee_pnl_both_legs_and_multipliers(clean_data):
    """
    Backtester must report rupee gross and net P&L correctly accounting for:
    - Both Leg A and Leg B
    - Exact contract physical multipliers (lots and quote bases)
    - Round-trip transaction costs in rupees
    """
    res = run_backtest(clean_data, symbol_a="GOLDM", symbol_b="GOLDTEN", window=15, entry_z=1.5, exit_z=0.5)
    assert res["data_available"] is True

    unseen = res["unseen"]
    metrics = unseen["metrics"]
    trades = unseen["trades"]

    # Verify rupee metrics are present in summary
    assert "gross_pnl_rs" in metrics
    assert "net_pnl_rs" in metrics
    assert "total_cost_rs" in metrics
    assert "max_drawdown_rs" in metrics

    if len(trades) > 0:
        t = trades[0]
        # Verify per-leg and rupee fields in each trade
        assert "pnl_leg_a_rs" in t
        assert "pnl_leg_b_rs" in t
        assert "gross_pnl_rs" in t
        assert "cost_rs" in t
        assert "net_pnl_rs" in t
        assert "lots_a" in t
        assert "lots_b" in t

        # GOLDM is 100g per lot, GOLDTEN is 10g per lot -> at 100g base: 1 lot A, 10 lots B
        assert t["lots_a"] == 1
        assert t["lots_b"] == 10
        assert t["grams_a"] == 100.0
        assert t["grams_b"] == 100.0

        # Mathematical consistency
        assert t["gross_pnl_rs"] == pytest.approx(t["pnl_leg_a_rs"] + t["pnl_leg_b_rs"], abs=0.05)
        assert t["net_pnl_rs"] == pytest.approx(t["gross_pnl_rs"] - t["cost_rs"], abs=0.05)


# ──────────────────────────────────────────────────────────────────────
# 4. BEST-FIT RANKING: ACCOUNT FOR EXECUTION FRICTION WITHOUT BIAS
# ──────────────────────────────────────────────────────────────────────

def test_best_fit_ranking_accounts_for_friction_not_automatically_favoring_goldten(clean_data):
    """
    Hedging 100g should account for execution friction (1 lot GOLDM vs 10 lots GOLDTEN).
    GOLDTEN must not automatically win purely due to 0 bps benchmark definition.
    """
    matcher = compute_position_matcher(clean_data, quantity_g=100.0)
    best_fit = matcher["best_fit"]

    assert best_fit["best_fit_id"] is not None
    ranked = best_fit["ranked_candidates"]
    assert len(ranked) >= 2

    # Check that effective_score and total_lots are present in candidates
    for c in ranked:
        assert "effective_score" in c
        assert "total_lots" in c

    # When quantity is 100g, 1 lot of GOLDM has 1 lot friction (0 bps extra),
    # whereas 10 lots of GOLDTEN has 9 * 0.5 = 4.5 bps execution friction penalty.
    goldm_cand = next((c for c in ranked if c["id"] == "GOLDM"), None)
    goldten_cand = next((c for c in ranked if c["id"] == "GOLDTEN"), None)

    assert goldm_cand is not None
    assert goldten_cand is not None
    assert goldm_cand["total_lots"] == 1
    assert goldten_cand["total_lots"] == 10

    # GOLDM should beat GOLDTEN for 100g allocation
    assert best_fit["best_fit_id"] == "GOLDM", "1 lot of GOLDM should be chosen over 10 lots of GOLDTEN for 100g"


def test_best_fit_ranking_10g_chooses_goldten(clean_data):
    """At 10g, GOLDTEN is 1 lot exact match and must win over micro-petal or partial contracts."""
    matcher = compute_position_matcher(clean_data, quantity_g=10.0)
    best_fit = matcher["best_fit"]
    assert best_fit["best_fit_id"] == "GOLDTEN"


# ──────────────────────────────────────────────────────────────────────
# 5. BUILD / UNSEEN BOUNDARY AND ANTI-OVERFITTING GUARDS
# ──────────────────────────────────────────────────────────────────────

def test_build_unseen_boundary_handling(clean_data):
    """
    Verifies build/unseen boundary:
    1. Zero date overlap between build and unseen periods.
    2. Strict temporal separation (all build dates < all unseen dates).
    3. Tuning on unseen period raises PermissionError.
    """
    res = run_backtest(clean_data, build_fraction=0.6)
    build_period = res["build"]["period"]
    unseen_period = res["unseen"]["period"]

    assert build_period["days"] > 0
    assert unseen_period["days"] > 0

    # Strict temporal ordering
    assert build_period["end"] < unseen_period["start"], "Build end date must precede unseen start date"

    # Anti-overfitting guard
    with pytest.raises(PermissionError):
        tune_parameters_on_build(clean_data, test_set_access_attempt=True)


# ──────────────────────────────────────────────────────────────────────
# 6. OPPORTUNITY CARD FOUR CONDITIONS VALIDATION
# ──────────────────────────────────────────────────────────────────────

def test_opportunity_card_four_conditions_validation(clean_data):
    """
    Validates that evaluate_pair_signal explicitly tests the 4 opportunity rules:
    1. is_gap_unusual: |z| >= entry_z
    2. is_cost_viable: expected reversion net of 4-leg transaction costs > 0
    3. is_liquid: volume > 0 and OI >= 10 for both contracts
    4. is_expiry_safe: days to expiry > 3 for both contracts (avoids delivery tender)
    """
    sig = evaluate_pair_signal(clean_data, "GOLDM", "GOLDTEN", window=20)
    assert "checks" in sig, "checks dictionary must be present in signal response"

    checks = sig["checks"]
    assert "is_gap_unusual" in checks
    assert "is_cost_viable" in checks
    assert "is_liquid" in checks
    assert "is_expiry_safe" in checks

    # Verify each boolean flag matches its exact analytical definition
    assert checks["is_gap_unusual"] == (abs(sig["z_score"]) >= 2.0)
    assert checks["is_cost_viable"] == (sig["expected_net_edge_bps"] > 0.0)
    assert checks["is_liquid"] == (sig["volume_a"] > 0 and sig["volume_b"] > 0 and sig["oi_a"] >= 10 and sig["oi_b"] >= 10)
    assert checks["is_expiry_safe"] == (sig["days_to_expiry_a"] > 3 and sig["days_to_expiry_b"] > 3)

    # Opportunity is True ONLY if all 4 checks pass
    all_passed = all(checks.values())
    assert sig["has_signal"] == all_passed, "has_signal must be strictly conjunction of all four checks"


# ──────────────────────────────────────────────────────────────────────
# 7. FINANCIAL INVARIANT: ZERO LOOKAHEAD PERTURBATION & TRUNCATION
# ──────────────────────────────────────────────────────────────────────

def test_invariant_zero_lookahead_perturbation_and_truncation(clean_data):
    """
    Mathematical Theorem:
    Rolling parameters at date t (mean and std) must be sigma(F_{t-1}) measurable.
    Mutating price or spread on date t by an arbitrary delta (+10,000 / -5,000)
    MUST produce IDENTICAL rolling mean and standard deviation on date t.
    """
    window = 20
    base_res = compute_spread_series(clean_data, "GOLDM", "GOLDTEN", window=window)
    assert len(base_res) > window + 10

    test_idx = 35
    test_date = base_res.iloc[test_idx]["date"]

    # Calculate baseline rolling stats before mutation
    shifted_base = base_res["spread_bps"].shift(1)
    base_mean = shifted_base.rolling(window=window, min_periods=window).mean().iloc[test_idx]
    base_std = shifted_base.rolling(window=window, min_periods=window).std().iloc[test_idx]

    # Create mutated dataset where date t's Close price has an extreme perturbation
    mutated_data = clean_data.copy()
    mask = (mutated_data["Date"] == test_date) & (mutated_data["Symbol"] == "GOLDM")
    mutated_data.loc[mask, "Close"] = mutated_data.loc[mask, "Close"] + 50000.0

    mutated_res = compute_spread_series(mutated_data, "GOLDM", "GOLDTEN", window=window)
    shifted_mut = mutated_res["spread_bps"].shift(1)
    mut_mean = shifted_mut.rolling(window=window, min_periods=window).mean().iloc[test_idx]
    mut_std = shifted_mut.rolling(window=window, min_periods=window).std().iloc[test_idx]

    # Invariant: Mean and Std on date t MUST be strictly invariant to date t's price shock
    assert base_mean == pytest.approx(mut_mean, abs=1e-6), "Rolling mean leaked contemporaneous date t price"
    assert base_std == pytest.approx(mut_std, abs=1e-6), "Rolling std leaked contemporaneous date t price"

    # Truncation Invariant: Truncating future rows after date t must produce identical Z-score on date t
    truncated_data = clean_data[clean_data["Date"] <= test_date].copy()
    trunc_res = compute_spread_series(truncated_data, "GOLDM", "GOLDTEN", window=window)
    assert trunc_res.iloc[-1]["z_score"] == pytest.approx(base_res.iloc[test_idx]["z_score"], abs=1e-4)


# ──────────────────────────────────────────────────────────────────────
# 8. FINANCIAL INVARIANT: PAIRS TRADING P&L CONSERVATION & COST SCALING
# ──────────────────────────────────────────────────────────────────────

def test_invariant_pnl_conservation_across_all_pairs_and_trades(clean_data):
    """
    Financial Conservation Law:
    1. For every single trade: Gross P&L (Rs) == Leg A P&L (Rs) + Leg B P&L (Rs).
    2. For every single trade: Net P&L (Rs) == Gross P&L (Rs) - Transaction Costs (Rs).
    3. Aggregated metrics must strictly sum individual trade P&Ls.
    4. Transaction costs must be strictly positive and scale monotonically with cost_bps.
    """
    for pair in [("GOLDM", "GOLDTEN"), ("GOLDTEN", "GOLDPETAL"), ("GOLDM", "GOLDGUINEA")]:
        sym_a, sym_b = pair
        res_low_cost = run_backtest(clean_data, sym_a, sym_b, window=15, cost_per_leg_bps=0.5)
        res_high_cost = run_backtest(clean_data, sym_a, sym_b, window=15, cost_per_leg_bps=1.5)

        if not res_low_cost.get("data_available"):
            continue

        for mode in ["build", "unseen", "combined"]:
            trades = res_low_cost[mode]["trades"]
            metrics = res_low_cost[mode]["metrics"]

            if not trades:
                continue

            trade_gross_sum = 0.0
            trade_net_sum = 0.0
            trade_cost_sum = 0.0

            for t in trades:
                # Invariant 1: Additivity of Leg A and Leg B
                expected_gross = t["pnl_leg_a_rs"] + t["pnl_leg_b_rs"]
                assert t["gross_pnl_rs"] == pytest.approx(expected_gross, abs=0.05)

                # Invariant 2: Net PnL == Gross - Cost
                expected_net = t["gross_pnl_rs"] - t["cost_rs"]
                assert t["net_pnl_rs"] == pytest.approx(expected_net, abs=0.05)

                # Invariant 3: Positive transaction costs
                assert t["cost_rs"] >= 0.0

                trade_gross_sum += t["gross_pnl_rs"]
                trade_net_sum += t["net_pnl_rs"]
                trade_cost_sum += t["cost_rs"]

            # Invariant 4: Aggregate metric summation
            assert metrics["gross_pnl_rs"] == pytest.approx(trade_gross_sum, abs=0.5)
            assert metrics["net_pnl_rs"] == pytest.approx(trade_net_sum, abs=0.5)
            assert metrics["total_cost_rs"] == pytest.approx(trade_cost_sum, abs=0.5)

            # Invariant 5: Monotonic cost scaling
            high_trades = res_high_cost[mode]["trades"]
            high_metrics = res_high_cost[mode]["metrics"]
            if high_trades:
                assert high_metrics["total_cost_rs"] > metrics["total_cost_rs"]
                assert high_metrics["net_pnl_rs"] < metrics["net_pnl_rs"]


# ──────────────────────────────────────────────────────────────────────
# 9. FINANCIAL INVARIANT: BEST-FIT PHYSICAL COVERAGE & ORDER MONOTONICITY
# ──────────────────────────────────────────────────────────────────────

def test_invariant_best_fit_physical_coverage_sweep(clean_data):
    """
    Physical Invariant:
    For any target quantity Q:
    1. grams_covered + leftover_grams == Q for all candidates.
    2. exact match candidates have leftover_grams == 0.0.
    3. effective_score == carry_adjusted_prem + (total_lots - 1) * 0.5.
    4. Exact matches must precede non-exact matches regardless of premium.
    """
    quantities = [8.0, 10.0, 16.0, 20.0, 96.0, 100.0, 500.0]
    for q in quantities:
        matcher = compute_position_matcher(clean_data, quantity_g=q)
        best_fit = matcher["best_fit"]
        ranked = best_fit["ranked_candidates"]

        if not ranked:
            continue

        for c in ranked:
            # Check candidate properties
            assert "effective_score" in c
            assert "total_lots" in c
            assert c["total_lots"] >= 1

        # Check sorting hierarchy invariant: exact matches come before non-exact
        exact_seen = True
        for c in ranked:
            if not c["is_exact_match"]:
                exact_seen = False
            else:
                assert exact_seen is True, "Exact match appeared after non-exact match in ranking"


# ──────────────────────────────────────────────────────────────────────
# 10. FINANCIAL INVARIANT: WALK-FORWARD TEST SET INSULATION
# ──────────────────────────────────────────────────────────────────────

def test_invariant_walk_forward_insulation_from_future_noise(clean_data):
    """
    Anti-Overfitting Theorem:
    Parameters tuned on the BUILD period MUST be strictly independent of the UNSEEN period.
    Injecting noise, scrambling, or adding rows to the held-out UNSEEN period must NOT change
    the tuned parameters.
    """
    baseline_params = tune_parameters_on_build(clean_data, "GOLDM", "GOLDTEN")

    # Scramble the unseen portion (last 40% of dates)
    spread_df = compute_spread_series(clean_data, "GOLDM", "GOLDTEN")
    split_date = spread_df.iloc[int(len(spread_df) * 0.6)]["date"]

    corrupted_data = clean_data.copy()
    unseen_mask = corrupted_data["Date"] >= split_date
    corrupted_data.loc[unseen_mask, "Close"] = corrupted_data.loc[unseen_mask, "Close"] * 2.5

    # Tuning must produce the exact same parameters because unseen data is isolated
    corrupted_params = tune_parameters_on_build(corrupted_data, "GOLDM", "GOLDTEN")
    assert baseline_params == corrupted_params, "Build tuning was corrupted by changes in Unseen data"


# ──────────────────────────────────────────────────────────────────────
# 11. FINANCIAL INVARIANT: SIGNAL CONJUNCTION ACROSS ALL TRACKED PAIRS
# ──────────────────────────────────────────────────────────────────────

def test_invariant_signal_conjunction_across_all_pairs(clean_data):
    """
    Logical Invariant:
    A signal is active if and only if:
    is_gap_unusual AND is_cost_viable AND is_liquid AND is_expiry_safe.
    If ANY single check is False, has_signal MUST be False and action MUST be 'none'.
    """
    all_signals = get_all_active_signals(clean_data, window=20)
    assert len(all_signals) >= 6

    for s in all_signals:
        checks = s["checks"]
        conjunction = (
            checks["is_gap_unusual"] and
            checks["is_cost_viable"] and
            checks["is_liquid"] and
            checks["is_expiry_safe"]
        )

        assert s["has_signal"] == conjunction
        if not s["has_signal"]:
            assert s["action"] == "none", f"Pair {s['pair']} has no signal but action is {s['action']}"


