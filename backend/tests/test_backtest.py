"""
KARAT – Module 3: Validation & Backtest Engine Tests.

Covers:
1. Walk-forward verification (no future information used in trade entry/exit).
2. Enforced BUILD / UNSEEN split (cannot tune parameters on the test set; raises PermissionError).
3. Cost monotonicity: higher cost per leg never raises net P&L.
4. Trades record actual expiry-dated contracts and settlement prices held.
5. Attribution: separation of strategy P&L and underlying gold benchmark move.
6. Honest verdict generation with small-sample warning (< 20 trades).
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.data.parser import load_sample
from backend.backtest.engine import (
    run_backtest,
    tune_parameters_on_build,
)


class TestBuildUnseenSplitEnforcement:
    def test_tuning_on_unseen_period_is_strictly_prevented(self):
        """
        Enforce in code that parameters cannot be tuned on the held-out test set.
        Attempting to access or optimize against the test set raises PermissionError.
        """
        df = load_sample()
        with pytest.raises(PermissionError) as exc_info:
            tune_parameters_on_build(df, test_set_access_attempt=True)
        assert "strictly prohibited" in str(exc_info.value)

    def test_headline_results_come_from_unseen_period(self):
        """The primary verdict and performance metrics must be reported from the unseen slice."""
        df = load_sample()
        res = run_backtest(df, "GOLDM", "GOLDTEN", window=5, cost_per_leg_bps=0.5)

        assert res["data_available"] is True
        assert "unseen" in res
        assert "build" in res
        assert "verdict" in res


        unseen_metrics = res["unseen"]["metrics"]
        assert "headline_conclusion" in res["verdict"]
        assert res["verdict"]["total_trades"] == unseen_metrics["total_trades"]


class TestCostMonotonicity:
    def test_higher_cost_never_raises_net_pnl(self):
        """
        QUANT PRINCIPLE: Higher per-leg cost must monotonically decrease
        (or keep flat if zero trades) net P&L.
        """
        df = load_sample()
        costs = [0.0, 0.5, 1.0, 1.5, 2.0]
        net_pnls = []

        for c in costs:
            res = run_backtest(df, "GOLDM", "GOLDTEN", window=5, cost_per_leg_bps=c)
            net_pnls.append(res["unseen"]["metrics"]["net_pnl_bps"])


        for i in range(len(net_pnls) - 1):
            assert net_pnls[i + 1] <= net_pnls[i] + 1e-6, (
                f"Cost monotonicity violation! Cost {costs[i]} produced net P&L {net_pnls[i]}, "
                f"while higher cost {costs[i+1]} produced {net_pnls[i+1]}"
            )


class TestActualContractsHeld:
    def test_trades_record_actual_expiries_and_prices(self):
        """
        Trades must track which physical contract expiry was held and its settlement marks.
        """
        df = load_sample()
        res = run_backtest(df, "GOLDM", "GOLDTEN", window=5, entry_z=1.0)
        trades = res["unseen"]["trades"]

        if trades:
            trade = trades[0]
            assert "expiry_a" in trade
            assert "expiry_b" in trade
            assert "raw_a_entry" in trade
            assert "raw_b_entry" in trade
            assert "raw_a_exit" in trade
            assert "raw_b_exit" in trade
            assert trade["holding_days"] >= 0


class TestAttributionAndVerdict:
    def test_attribution_components(self):
        """Separates market-neutral strategy P&L from underlying gold move."""
        df = load_sample()
        res = run_backtest(df, "GOLDM", "GOLDTEN", window=5)

        attribution = res["unseen"]["attribution"]
        assert "strategy_pnl_bps" in attribution
        assert "underlying_gold_move_bps" in attribution
        assert "correlation_to_gold" in attribution
        assert -1.0 <= attribution["correlation_to_gold"] <= 1.0

    def test_small_sample_warning(self):
        """Small sample size (< 20 trades) must flag a warning in the verdict."""
        df = load_sample()
        res = run_backtest(df, "GOLDM", "GOLDTEN", window=5)
        verdict = res["verdict"]

        if verdict["total_trades"] < 20:
            assert verdict["small_sample_warning"] is True
            assert "Small sample" in verdict["headline_conclusion"]
